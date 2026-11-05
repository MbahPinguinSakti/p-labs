# Lapisan LLM: cara kerja dan cara mengembangkannya

Panduan ini menjelaskan kode di `platform/llm/` dari nol: masalah yang dipecahkan, pola yang dipakai, dan cara menambah provider sendiri. Baca sambil membuka file-nya.

## 1. Masalahnya

Evaluator (`evaluate.py`) hanya butuh satu hal dari LLM: *kirim system prompt + pesan user, dapatkan JSON yang sesuai schema*. Tapi setiap provider punya cara sendiri:

| | Anthropic | OpenAI & kawan-kawan | Lainnya |
|---|---|---|---|
| Endpoint | `/v1/messages` | `/v1/chat/completions` | macam-macam |
| System prompt | parameter `system` | pesan `role: system` | macam-macam |
| JSON terjamin | `output_config.format` | `response_format` | kadang tidak ada |
| Error | `anthropic.RateLimitError`, ... | HTTP 429, ... | macam-macam |

Kalau `evaluate.py` harus tahu semua perbedaan ini, kodenya penuh `if provider == ...`. Solusinya: **satu kontrak**, dan setiap provider punya **adapter** yang menerjemahkan kontrak itu ke API-nya masing-masing.

```
evaluate.py ──> get_backend("groq") ──> OpenAICompatibleBackend ──> api.groq.com
                     │
                     └── kontraknya selalu sama:
                         data, meta = backend.complete_json(system, user, schema)
```

## 2. Peta file

| File | Isi |
|---|---|
| `base.py` | Kontrak (`Backend`), error, parser JSON, registry |
| `anthropic_backend.py` | Claude lewat SDK resmi: API langsung, Bedrock, Vertex |
| `openai_compat.py` | Semua server berformat OpenAI + daftar preset provider |
| `litellm_backend.py` | Catch-all lewat LiteLLM (100+ provider) |
| `__init__.py` | Mengimpor semua backend supaya terdaftar |
| `../tests/test_llm.py` | Test offline dengan server tiruan |

## 3. Pola 1: kontrak lewat kelas dasar

Buka `base.py`, kelas `Backend`. Ia punya dua method:

```python
class Backend:
    def _call(self, system, user, schema, structured):
        """Kirim satu request. Kembalikan (teks_jawaban, meta_dict)."""
        raise NotImplementedError

    def complete_json(self, system, user, schema):
        ...  # memanggil _call, menangani fallback, mem-parse JSON
```

- `complete_json` adalah method **publik**, yang dipanggil `evaluate.py`. Isinya sama untuk semua provider, jadi ditulis sekali saja di kelas dasar.
- `_call` (garis bawah = "internal") adalah satu-satunya bagian yang **berbeda** per provider. Setiap subclass wajib mengisinya.

Pola ini disebut *template method*: kerangka alurnya di kelas dasar, detailnya di subclass. Keuntungannya, logika yang rumit (fallback, parsing) tidak ditulis ulang di setiap backend.

## 4. Pola 2: fallback structured output → instruksi

Tidak semua server bisa *dipaksa* mengeluarkan JSON yang valid. Alurnya di `complete_json`:

```
_call(structured=True)            # minta JSON schema secara resmi
   │
   ├─ berhasil ─────────────────> parse_json_text(teks)
   │
   └─ StructuredOutputUnsupported # server menolak (mis. HTTP 400)
        │
        └─> _call(structured=False, user + "Balas HANYA JSON sesuai schema: ...")
                 └─> parse_json_text(teks)   # bersihkan ```json, ambil {...}
```

Perhatikan dua jenis error:
- `StructuredOutputUnsupported` = "fitur ini tidak ada, coba cara lain". Error ini **internal**, ditangkap `complete_json` sendiri.
- `LLMError` = "gagal, menyerah" (key salah, rate limit, jaringan putus). Error ini diteruskan ke `evaluate.py`.

Membedakan "bisa dicoba cara lain" dari "gagal total" adalah keputusan desain yang penting. Kalau semua error disamakan, fallback akan ikut jalan saat API key salah dan membuang satu request lagi.

`meta["structured_output"]` mencatat mode yang akhirnya dipakai, supaya kamu tahu kalau sebuah model ternyata jalan di mode instruksi (kurang andal).

### Lapis kedua: "diterima" belum tentu "ditegakkan"

Uji dengan LLM sungguhan (9Router → Gemini, 2026-11-03) membuktikan asumsi di atas belum cukup. Gateway itu **menerima** `response_format` tanpa error 400, tapi tidak meneruskannya ke model. Hasilnya JSON salah bentuk: `checkpoints` alih-alih `llm_checkpoints`, field wajib hilang, string di tempat array.

Karena itu, `complete_json` sekarang selalu memvalidasi hasilnya dengan `schema_errors()`, validator mini di `base.py` tanpa dependency yang mendukung subset JSON Schema yang kita pakai. Kalau ada pelanggaran:

```
parse_json_text(teks) ─> schema_errors(data, schema)
   │
   ├─ kosong ──────────────────> selesai
   │
   └─ ada error ─> 1x retry mode instruksi:
                     prompt + schema + jawaban lama + daftar error berpath
                     │
                     ├─ valid ──> meta: schema_retry=True, structured_output=False
                     └─ masih salah ──> LLMError
```

Error-nya memakai path (`$.feedback.key_moments[0].note: wajib ada`) supaya bisa dikirim balik ke model apa adanya. Retry mengirim ulang seluruh prompt, jadi biayanya sekitar 2× token (`meta["usage_first"]` mencatat usage percobaan pertama).

## 5. Pola 3: registry + decorator

Bagaimana `get_backend("groq")` tahu harus membuat objek apa? Lewat kamus `REGISTRY` di `base.py`, yang diisi oleh decorator `@register`:

```python
@register("anthropic", "Claude via API Anthropic (default)", needs=["ANTHROPIC_API_KEY"])
def _anthropic(model):
    return AnthropicBackend(model, "anthropic")
```

`@register(...)` dijalankan **saat modul diimpor**, dan hasilnya sama dengan menulis:

```python
REGISTRY["anthropic"] = {"factory": _anthropic, "description": "...", "needs": (...)}
```

Karena itu `__init__.py` wajib mengimpor setiap modul backend. Tanpa import itu, decorator-nya tidak pernah jalan dan provider-nya tidak terdaftar.

Kenapa disimpan **fungsi pembuat** (factory), bukan objek backend-nya langsung? Karena membuat backend bisa gagal (SDK belum terinstall, key belum diset). Dengan factory, kegagalan itu baru terjadi saat provider tersebut benar-benar dipilih, bukan saat program start.

### Jebakan: closure di dalam loop

`openai_compat.py` mendaftarkan semua preset sekaligus lewat loop:

```python
def _make(preset):
    return lambda model: OpenAICompatibleBackend(model, preset)

for _name, ... in PRESETS.items():
    register(_name, ...)(_make(_name))
```

Kenapa tidak langsung `register(_name)(lambda model: OpenAICompatibleBackend(model, _name))`? Karena lambda di Python mengingat **variabel**, bukan **nilai**-nya. Setelah loop selesai, `_name` bernilai preset terakhir (`"openai-compatible"`), sehingga *semua* lambda akan membuat backend `openai-compatible`. Fungsi `_make` membuat scope baru untuk setiap preset, jadi tiap lambda mengunci nilainya sendiri. Bug ini sangat umum; coba buktikan sendiri:

```python
fs = [lambda: i for i in range(3)]
print([f() for f in fs])   # [2, 2, 2], bukan [0, 1, 2]
```

## 6. Pola 4: menerjemahkan error

Setiap provider melempar error dengan bentuknya sendiri. Backend menerjemahkannya ke `LLMError` dengan pesan yang bisa ditindaklanjuti:

```python
except a.AuthenticationError as e:
    raise LLMError(f"Kredensial {self.platform} tidak valid") from e
except a.RateLimitError as e:
    raise LLMError(f"Rate limit: {e.message}") from e
except a.APIStatusError as e:          # induk dari dua kelas di atas
    raise LLMError(f"API error {e.status_code}: {e.message}") from e
```

Dua hal yang perlu diperhatikan:
- **Urutan `except` dari yang paling spesifik.** `RateLimitError` adalah turunan `APIStatusError`. Kalau `APIStatusError` ditulis duluan, ia menangkap semuanya dan cabang `RateLimitError` tidak pernah jalan.
- **`from e`** menyimpan error aslinya. Pesan untuk user tetap rapi, tapi traceback lengkap tetap ada saat debugging.

## 7. Pola 5: konfigurasi lewat env

Prioritasnya: argumen CLI (`--provider`, `--model`) > env (`LAB_LLM_PROVIDER`, `LAB_LLM_MODEL`) > default (`anthropic`, `claude-opus-5-5`). Lihat `get_backend` di `base.py`. API key **tidak pernah** ditulis di kode atau file konfigurasi project, melainkan selalu dibaca dari env.

| Env | Dipakai oleh |
|---|---|
| `LAB_LLM_PROVIDER`, `LAB_LLM_MODEL` | semua |
| `LAB_LLM_EFFORT` | anthropic (`low`/`medium`/`high`/`xhigh`/`max`, default `high`) |
| `LAB_LLM_BASE_URL` | openai-compatible (override URL preset), litellm |
| `LAB_LLM_API_KEY` | openai-compatible (override env key preset) |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, ... | key per provider |

## 8. Cara pakai

```bash
python3 platform/evaluate.py providers                       # daftar provider + env yang kurang
python3 platform/evaluate.py llm-test --provider ollama --model qwen3   # uji koneksi, request kecil

# Claude (default)
pip install anthropic && export ANTHROPIC_API_KEY=...
python3 platform/evaluate.py run labs/net-001

# OpenAI / Gemini / Groq / ... : nama preset + model + key
export GEMINI_API_KEY=... 
python3 platform/evaluate.py run labs/net-001 --provider gemini --model <nama-model>

# Model lokal tanpa biaya
python3 platform/evaluate.py run labs/net-001 --provider ollama --model <model-yang-sudah-di-pull>

# Server OpenAI-compatible lain
LAB_LLM_BASE_URL=https://host-saya/v1 LAB_LLM_API_KEY=... \
  python3 platform/evaluate.py run labs/net-001 --provider openai-compatible --model <model>

# Sisanya lewat LiteLLM (Azure, Bedrock non-Claude, Cohere, ...)
pip install litellm
python3 platform/evaluate.py run labs/net-001 --provider litellm --model azure/<deployment>
```

Nama model tidak di-hardcode (kecuali Claude), karena daftar model tiap provider berubah terus. Cek dokumentasi provider untuk nama yang berlaku.

Catatan kualitas: evaluator ini butuh model yang kuat untuk membaca timeline ~20 ribu token dan menilai methodology. Model kecil (lokal 7–8B) biasanya jalan, tapi penilaiannya kurang konsisten. Ukur dengan `evaluate.py check ... --repeat 5` sebelum mempercayainya.

## 9. Menjalankan test

```bash
python3 -m unittest discover -s platform/tests -v
```

Test berjalan tanpa internet dan tanpa API key. `MockServer` di `test_llm.py` adalah server HTTP kecil di localhost yang meniru OpenAI (`/v1/chat/completions`) dan Anthropic (`/v1/messages`). Trik utamanya: backend diarahkan ke server tiruan lewat env (`LAB_LLM_BASE_URL`, `ANTHROPIC_BASE_URL`), jadi kode backend yang diuji persis sama dengan yang dipakai sungguhan. Test untuk SDK `anthropic`/`litellm` otomatis dilewati kalau paketnya belum terinstall.

Baca `TestOpenAICompatible.test_fallback_to_instruction_mode`: server tiruan menolak request pertama dengan 400, lalu test memeriksa bahwa request kedua dikirim tanpa `response_format` dan dengan schema di dalam prompt. Begitulah cara menguji alur di bagian 4 tanpa provider sungguhan.

## 10. Latihan

Kerjakan berurutan. Setelah tiap latihan, jalankan test.

### Latihan 1: tambah preset (5 menit)
Tambahkan satu provider OpenAI-compatible yang belum ada (mis. Fireworks, Cerebras, atau server di kantormu) ke `PRESETS` di `openai_compat.py`. Cukup satu baris: nama, base URL dari dokumentasi provider, nama env API key, deskripsi. Cek hasilnya dengan `evaluate.py providers`.

**Pertanyaan:** kenapa kamu tidak perlu mengubah `evaluate.py` sama sekali?

### Latihan 2: backend "replay" (30 menit)
Buat `platform/llm/replay_backend.py`: backend yang **tidak memanggil LLM**, tapi membaca jawaban dari file JSON. Berguna untuk mengulang evaluasi dengan jawaban LLM yang sama persis (deterministik) dan untuk demo tanpa biaya.

Kerangka:

```python
import os
from pathlib import Path

from .base import Backend, LLMError, register


class ReplayBackend(Backend):
    name = "replay"

    def __init__(self, path):
        super().__init__(model="replay")
        # TODO: simpan path; lempar LLMError kalau path kosong atau file tidak ada

    def _call(self, system, user, schema, structured):
        # TODO: baca isi file, kembalikan (teks, meta)
        # Petunjuk: tidak perlu mem-parse JSON di sini. Kenapa?
        ...


@register("replay", "Jawaban dari file (LAB_LLM_REPLAY_FILE)", needs=["LAB_LLM_REPLAY_FILE"])
def _replay(model):
    return ReplayBackend(os.environ.get("LAB_LLM_REPLAY_FILE"))
```

Jangan lupa mendaftarkannya di `__init__.py`. Uji dengan mengambil satu `llm_runs[0].output` dari `evaluation.json` hasil run sungguhan, simpan ke file, lalu:

```bash
LAB_LLM_REPLAY_FILE=jawaban.json python3 platform/evaluate.py run labs/net-001/golden/20261019-234339 --provider replay
```

### Latihan 3: test untuk backend-mu (20 menit)
Tambahkan kelas `TestReplay` di `test_llm.py` yang memeriksa: (a) jawaban dari file terbaca dan ter-parse, (b) file yang tidak ada menghasilkan `LLMError`. Gunakan `tempfile.NamedTemporaryFile` untuk membuat file sementara. Contoh paling dekat: `TestRegistry.test_custom_backend`.

### Latihan 4 (lanjutan): backend native tanpa OpenAI-compat
Pilih satu provider yang punya API sendiri (mis. API native Gemini, atau Cohere). Tulis backend dengan `urllib` seperti `openai_compat.py`, lalu tentukan sendiri: request mana yang dianggap `StructuredOutputUnsupported` dan mana yang `LLMError`? Tulis test-nya dengan `MockServer` yang meniru format provider itu.

## 11. Debugging

- `evaluate.py llm-test --provider X` dulu, sebelum evaluasi penuh. Request-nya kecil, murah, dan langsung memperlihatkan `meta` (model yang menjawab, usage, mode structured output).
- `evaluate.py run ... --dry-run` menulis prompt lengkap ke `evaluator_prompt.md`, tanpa memanggil LLM.
- `meta.schema_retry: true` berarti server mengabaikan schema dan output baru valid setelah diperbaiki. `meta.schema_errors_first` memperlihatkan kesalahan percobaan pertama.
- Router/proxy yang membalas `text/event-stream` meski tidak diminta: `openai_compat.py` sekarang selalu mengirim `"stream": false`. Kalau masih terjadi, error-nya berbunyi "respons bukan JSON".
- `evaluation.json` menyimpan `meta` dan `warnings` setiap run. Warning seperti "event tidak dikenal" biasanya tanda modelnya terlalu lemah atau berhalusinasi.
