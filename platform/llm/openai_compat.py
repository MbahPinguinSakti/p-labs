"""Backend untuk semua server yang meniru endpoint OpenAI /chat/completions.

Banyak provider (dan semua server model lokal populer) memakai format ini,
jadi satu kelas cukup; yang berbeda hanya base URL dan nama env API key-nya.
Tanpa dependency: HTTP pakai urllib dari stdlib.

Base URL di PRESETS bisa berubah sewaktu-waktu. Kalau provider memindahkan
endpoint, override dengan LAB_LLM_BASE_URL tanpa mengubah kode.
"""

import json
import os
import urllib.error
import urllib.request

from .base import Backend, LLMError, StructuredOutputUnsupported, register

# nama: (base_url, env API key atau None untuk server lokal, deskripsi)
PRESETS = {
    "openai":     ("https://api.openai.com/v1", "OPENAI_API_KEY", "OpenAI"),
    "gemini":     ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "Google Gemini (endpoint OpenAI-compatible)"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "OpenRouter (ratusan model, satu key)"),
    "groq":       ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "Groq"),
    "deepseek":   ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY", "DeepSeek"),
    "mistral":    ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", "Mistral"),
    "together":   ("https://api.together.xyz/v1", "TOGETHER_API_KEY", "Together AI"),
    "xai":        ("https://api.x.ai/v1", "XAI_API_KEY", "xAI"),
    "ollama":     ("http://localhost:11434/v1", None, "Ollama (lokal)"),
    "lmstudio":   ("http://localhost:1234/v1", None, "LM Studio (lokal)"),
    "vllm":       ("http://localhost:8000/v1", None, "vLLM (lokal)"),
    "9router":    ("http://localhost:20128/v1", None, "9Router (lokal)"),
    # Server lain apa pun: wajib LAB_LLM_BASE_URL, key opsional di LAB_LLM_API_KEY.
    "openai-compatible": (None, None, "Server OpenAI-compatible lain (set LAB_LLM_BASE_URL)"),
}

# Model default per preset, dipakai kalau --model / LAB_LLM_MODEL kosong.
# Hanya untuk preset yang modelnya sudah teruji sebagai evaluator.
DEFAULT_MODELS = {
    "9router": "ag/claude-sonnet-4-6",  # golden net-001 16/16, spread 0 (2026-11-03)
}


class OpenAICompatibleBackend(Backend):
    def __init__(self, model, preset="openai-compatible", timeout=600):
        model = model or DEFAULT_MODELS.get(preset)
        if not model:
            raise LLMError(f"LAB_LLM_MODEL wajib diisi untuk provider {preset}")
        super().__init__(model)
        default_url, key_env, _ = PRESETS[preset]
        self.name = preset
        self.base_url = (os.environ.get("LAB_LLM_BASE_URL") or default_url or "").rstrip("/")
        if not self.base_url:
            raise LLMError("Set LAB_LLM_BASE_URL untuk provider openai-compatible")
        self.api_key = os.environ.get("LAB_LLM_API_KEY") or (os.environ.get(key_env) if key_env else None)
        if key_env and not self.api_key:
            raise LLMError(f"Set {key_env} (atau LAB_LLM_API_KEY) untuk provider {preset}")
        self.timeout = timeout

    def _post(self, body):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions",
                                     data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            raw = r.read()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            # Mis. server yang tetap membalas SSE (text/event-stream).
            raise LLMError(f"{self.name}: respons bukan JSON: {raw[:120]!r}") from e

    def _call(self, system, user, schema, structured):
        body = {
            "model": self.model,
            # Eksplisit: spesifikasi OpenAI default-nya false, tapi beberapa
            # router (mis. 9Router) default-nya streaming SSE.
            "stream": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }
        if structured:
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "evaluation", "schema": schema, "strict": True}}
        try:
            data = self._post(body)
        except urllib.error.HTTPError as e:
            with e:  # tutup koneksi error-nya juga
                detail = e.read()[:300].decode(errors="replace")
            # 400/422 saat structured: anggap server tidak mendukung json_schema.
            if structured and e.code in (400, 422):
                raise StructuredOutputUnsupported(detail) from e
            if e.code in (401, 403):
                raise LLMError(f"{self.name}: API key ditolak ({e.code})") from e
            if e.code == 404:
                raise LLMError(f"{self.name}: endpoint/model tidak ditemukan ({self.model})") from e
            if e.code == 429:
                raise LLMError(f"{self.name}: rate limit") from e
            raise LLMError(f"{self.name} error {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise LLMError(f"Tidak bisa terhubung ke {self.base_url}: {e.reason}") from e
        except TimeoutError as e:
            raise LLMError(f"Timeout setelah {self.timeout} detik") from e

        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"Format respons tidak dikenal: {str(data)[:200]}") from e
        if choice.get("finish_reason") == "length":
            raise LLMError("Output terpotong (length)")
        return text, {"provider": self.name, "model": data.get("model", self.model),
                      "base_url": self.base_url, "usage": data.get("usage")}


def _make(preset):
    return lambda model: OpenAICompatibleBackend(model, preset)


for _name, (_url, _key, _desc) in PRESETS.items():
    _needs = ([] if _name in DEFAULT_MODELS else ["LAB_LLM_MODEL"]) + ([_key] if _key else [])
    if _name in DEFAULT_MODELS:
        _desc += f" [default: {DEFAULT_MODELS[_name]}]"
    register(_name, _desc, needs=_needs)(_make(_name))
