# Arsitektur

Semua komponen berjalan di satu mesin, dan tidak ada database. State satu sesi
disimpan sebagai file di `labs/<id>/.state/`, jadi setiap tahap bisa diperiksa
dan diulang dari file.

```
 browser ──HTTP/WebSocket──▶ platform/server.py (FastAPI, :8000)
    │                          ├─ katalog soal      labs/*/problem.yaml
    │                          ├─ DeployJobs        labs/<id>/reset.sh → platform/reset-lab → containerlab
    │                          ├─ Runtime           ttyd (:7681) + checkpoints.py watch
    │                          ├─ EvalJobs          evaluate.py → verify.sh + scoring.py + llm/
    │                          └─ WebSocket         push state saat file di .state/ berubah
    │
    └──iframe──▶ ttyd ──▶ platform/lab-shell <lab> <node>
                              ├─ script (util-linux)  → .state/tty/<node>-*.log + .timing
                              ├─ node Linux:    docker exec bash --rcfile /etc/lab/rc
                              │                   └─ lab-rc.sh (hook PROMPT_COMMAND) → .state/events/<node>.jsonl
                              └─ node RouterOS: ros.py shell ──SSH──▶ CHR (VM di container vrnetlab)
                                                  └─ event ditulis dari host → .state/events/<node>.jsonl
```

## Alur satu sesi

1. **Deploy** (`reset-lab`): destroy, buat `.state/`, lalu `containerlab
   deploy`, `verify.sh` (harus 100), dan `inject.sh` (fault +
   `ground_truth.json`). `session_id` ditulis **paling akhir**, jadi sesi baru
   dianggap ada kalau semua tahap berhasil.
2. **Bermain**: setiap command yang selesai di node ditulis oleh hook bash
   sebagai satu baris JSON (command, exit code, waktu). Di sisi host, `script`
   merekam input dan output mentah terminal.
3. **Checkpoint live**: `checkpoints.py watch` membaca event baru, mencocokkan
   `command_match`, dan menjalankan `state_check` di node yang baru menerima
   command. Hasilnya ditulis ke `checkpoints.jsonl`.
4. **Push ke UI**: server memantau ukuran dan mtime file di `.state/`. Kalau ada
   yang berubah, server mengirim state yang **sudah disaring**: tanpa ground
   truth, tanpa parameter, dan tanpa detail checkpoint `hidden`.
5. **Penilaian** (`evaluate.py`):
   - `verify.sh` memberi correctness;
   - `transcript.py` menyusun timeline E-id dengan output per command;
   - `scoring.py` menghitung efficiency, safety, hint, dan process gate;
   - LLM (lewat `llm/`, dengan provider bebas) menerima transcript, ground
     truth, dan rubrik, lalu mengembalikan JSON berskema berisi methodology,
     llm_judge, feedback, dan momen kunci, semuanya dengan rujukan event.
6. **Arsip**: `.state/` disalin ke `sessions/<sesi>/`. Halaman Hasil, Progress,
   dan Leaderboard membaca dari arsip ini.

## Isi `.state/`

| File | Ditulis oleh | Isi |
|---|---|---|
| `session_id` | reset-lab / sessions.rearm | `YYYYmmdd-HHMMSS` |
| `ground_truth.json` | inject.sh | nilai fault yang sebenarnya (privat) |
| `events/<node>.jsonl` | lab-rc.sh (di node) | satu baris per command |
| `events/host.jsonl` | lab-shell, hints.py | `shell_open`/`shell_close`, `hint` |
| `tty/<node>-*.log`, `.timing` | script | rekaman terminal mentah (untuk output per command) |
| `checkpoints.jsonl` | checkpoints.py watch | checkpoint yang tercapai + bukti |
| `verify.json` | evaluate.py | hasil verify.sh saat dinilai |
| `evaluator_prompt.md` | evaluate.py | prompt lengkap yang dikirim ke LLM |
| `evaluation.json`, `.md` | evaluate.py | hasil akhir (mesin / manusia) |

## Batas keamanan

- **Pemain tidak boleh melihat jawaban.** Satu-satunya jalur dari server ke
  browser adalah `live_state()` dan `session_result()`. `tests/test_server.py`
  memastikan ground truth, parameter, dan checkpoint tersembunyi tidak bocor
  sebelum sesi dinilai.
- **ttyd hanya listen di `lo`** (`-i lo`) dan hanya menjalankan `lab-shell`,
  yang menolak nama node di luar `[a-z0-9-]`.
- **Node lab tidak punya jaringan management** (`network-mode: none`), jadi
  node hanya bisa saling menjangkau lewat link soal.
- **Evaluator AI hanya membaca.** LLM menerima transcript dan tidak punya tool
  untuk mengeksekusi apa pun di lab.
- **Hak root containerlab** didapat lewat sudo atau mode setuid `clab_admins`
  ([instalasi](instalasi.md#deploy-lab-tanpa-sudo)). Server sendiri berjalan
  sebagai user biasa.

## Modul `platform/`

| File | Peran |
|---|---|
| `server.py` | API + WebSocket + file statis web UI |
| `reset-lab`, `sessions.py` | siklus hidup sesi: deploy, rearm tanpa deploy, arsip |
| `lab-shell`, `lab-rc.sh`, `serve` | perekaman terminal |
| `ros.py` | shell proxy RouterOS (prompt, konteks menu, SSH, event) + `exec` untuk inject/verify/state_check |
| `checkpoints.py` | matcher checkpoint (watch live + status) |
| `hints.py`, `lab-hint` | hint berjenjang yang tercatat |
| `transcript.py` | event → timeline E-id, klasifikasi perubahan state per NOS |
| `scoring.py` | rumus deterministik |
| `evaluate.py`, `report.py`, `prompts/` | evaluator dan laporan |
| `llm/` | lapisan provider LLM ([README](../platform/llm/README.md)) |
| `autoplay.py` | memainkan skenario otomatis → golden transcript |
| `lablint.py`, `newlab.py`, `templates/lab/` | membuat dan memeriksa soal |
| `install-service.sh`, `setup-sudoless.sh`, `build-routeros-image.sh` | dipanggil installer |
| `_venv.py` | menjalankan ulang script CLI dengan Python `.venv` |
