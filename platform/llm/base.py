"""Kontrak bersama semua backend LLM + registry provider.

Penjelasan lengkap pola di file ini ada di README.md di direktori yang sama.
"""

import json
import os
import re


class LLMError(RuntimeError):
    """Satu-satunya error yang perlu ditangkap pemanggil (evaluate.py)."""


class StructuredOutputUnsupported(Exception):
    """Dilempar backend kalau server menolak mode structured output (JSON schema).

    Backend.complete_json menangkapnya lalu mengulang dengan mode instruksi.
    """


class Backend:
    """Kelas dasar. Subclass cukup mengisi `_call`.

    Alurnya (pola *template method*):
      1. complete_json memanggil _call(structured=True): server dipaksa
         mengeluarkan JSON yang valid terhadap schema.
      2. Kalau server tidak mendukung itu, _call melempar
         StructuredOutputUnsupported, lalu complete_json mengulang dengan
         structured=False: schema ditempel ke prompt sebagai instruksi.
      3. Teks hasil di-parse jadi dict (pagar ```json dibersihkan).
    """

    name = "base"

    def __init__(self, model):
        self.model = model

    def _call(self, system, user, schema, structured):
        """Kirim satu request. Kembalikan (teks_jawaban, meta_dict)."""
        raise NotImplementedError

    def complete_json(self, system, user, schema):
        try:
            text, meta = self._call(system, user, schema, structured=True)
        except StructuredOutputUnsupported:
            text, meta = self._call(system, user + "\n\n" + json_instruction(schema), schema, structured=False)
            meta["structured_output"] = False
        else:
            # "Diterima" belum tentu "ditegakkan": gateway seperti 9Router
            # menerima response_format tanpa error lalu mengabaikannya.
            meta["structured_output"] = True
        data = parse_json_text(text)
        errors = schema_errors(data, schema)
        if errors:
            # Satu kali perbaikan, mode instruksi: schema ditempel di prompt
            # (satu-satunya cara model "melihat" schema kalau server
            # mengabaikannya) + daftar kesalahan + jawaban lama untuk diperbaiki.
            repair = (user + "\n\n" + json_instruction(schema) +
                      "\n\nJawaban sebelumnya tidak sesuai schema:\n" + text[:20000] +
                      "\n\nKesalahan:\n- " + "\n- ".join(errors[:15]) +
                      "\n\nPerbaiki dan kirim ulang JSON lengkap yang valid.")
            first_usage = meta.get("usage")
            text, meta = self._call(system, repair, schema, structured=False)
            meta.update(structured_output=False, schema_retry=True,
                        schema_errors_first=errors[:15], usage_first=first_usage)
            data = parse_json_text(text)
            errors = schema_errors(data, schema)
            if errors:
                raise LLMError("Output tidak sesuai schema setelah 1x perbaikan: "
                               + "; ".join(errors[:5]))
        return data, meta


def json_instruction(schema):
    return ("Balas HANYA dengan satu objek JSON (tanpa teks lain, tanpa markdown) "
            "yang valid terhadap JSON Schema berikut:\n" + json.dumps(schema, ensure_ascii=False))


_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool,
          "integer": int, "number": (int, float)}


def schema_errors(value, schema, path="$"):
    """Validator JSON Schema mini (subset yang dipakai project ini).

    Mendukung: type, enum, properties, required, additionalProperties: false,
    items. Mengembalikan daftar pesan error berisi path, kosong kalau valid.
    """
    expected = schema.get("type")
    if expected:
        ok = isinstance(value, _TYPES[expected])
        # bool adalah subclass int di Python: True bukan "integer".
        if expected in ("integer", "number") and isinstance(value, bool):
            ok = False
        if not ok:
            return [f"{path}: harus {expected}, dapat {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: {value!r} bukan salah satu dari {schema['enum']}"]

    errors = []
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: wajib ada")
        for key, item in value.items():
            if key in props:
                errors += schema_errors(item, props[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: field tidak dikenal")
    elif isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors += schema_errors(item, schema["items"], f"{path}[{i}]")
    return errors


FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$", re.S)


def parse_json_text(text):
    """Model tanpa structured output kadang membungkus JSON dengan ```json."""
    if not text or not text.strip():
        raise LLMError("Respons kosong")
    m = FENCE.match(text)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Upaya terakhir: ambil objek {...} terluar.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise LLMError(f"Output bukan JSON valid: {text[:200]!r}") from None


# --- registry ------------------------------------------------------------------

# nama provider -> (factory(model) -> Backend, deskripsi, env yang dibutuhkan)
REGISTRY = {}


def register(name, description, needs=()):
    """Decorator: daftarkan fungsi pembuat backend dengan nama provider."""
    def deco(factory):
        REGISTRY[name] = {"factory": factory, "description": description, "needs": tuple(needs)}
        return factory
    return deco


def get_backend(provider=None, model=None):
    """provider/model: argumen > env LAB_LLM_PROVIDER / LAB_LLM_MODEL > default."""
    provider = provider or os.environ.get("LAB_LLM_PROVIDER") or "anthropic"
    model = model or os.environ.get("LAB_LLM_MODEL")
    if provider not in REGISTRY:
        raise LLMError(f"Provider tidak dikenal: {provider}. Lihat: evaluate.py providers")
    return REGISTRY[provider]["factory"](model)


def list_providers():
    """[(nama, deskripsi, env_yang_belum_diset)]"""
    out = []
    for name, info in REGISTRY.items():
        missing = [v for v in info["needs"] if not os.environ.get(v)]
        out.append((name, info["description"], missing))
    return out
