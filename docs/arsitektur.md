# Arsitektur

[Beranda](../README.md) › Arsitektur

Semua komponen berjalan di satu mesin, dan state lab tidak memakai database
(hanya akun mode Server yang disimpan di SQLite). State satu sesi
disimpan sebagai file di direktori `.state/` milik instance lab (di install
pribadi: `labs/<id>/.state/`), jadi setiap tahap bisa diperiksa dan diulang
dari file.

```
 browser ──HTTP/WebSocket──▶ platform/server.py (FastAPI, :8000)
    │                          ├─ katalog soal      labs/*/problem.yaml
    │                          ├─ DeployJobs        labs/<id>/reset.sh → platform/reset-lab → containerlab
    │                          ├─ Runtimes          checkpoints.py watch, satu per instance
    │                          ├─ EvalJobs          evaluate.py → verify.sh + scoring.py + llm/
    │                          └─ WebSocket         push state saat file di .state/ berubah
    │
    └──WebSocket /api/labs/<id>/term/<node>──▶ termbridge.py (PTY) ──▶ platform/lab-shell <lab> <node>
                              ├─ script (util-linux)  → .state/tty/<node>-*.log + .timing
                              ├─ node Linux:    docker exec bash --rcfile /etc/lab/rc
                              │                   └─ lab-rc.sh (hook PROMPT_COMMAND) → .state/events/<node>.jsonl
                              └─ node RouterOS: ros.py shell ──SSH──▶ CHR (VM di container vrnetlab)
                                                  └─ event ditulis dari host → .state/events/<node>.jsonl
```

## Soal dan instance

Soal (`labs/<id>/`: problem.yaml, topologi, script) hanya definisi. Yang
berjalan adalah **instance**: satu soal yang dideploy untuk satu user, dengan
nama lab containerlab, container, dan `.state/` sendiri, sehingga beberapa user
bisa memainkan soal yang sama bersamaan (`platform/instance.py`).

| | instance `local` (install pribadi) | instance user lain (`<user>`) |
|---|---|---|
| direktori | `labs/<id>/` | `<instances>/<user>/<id>/` |
| state sesi | `labs/<id>/.state/` | `<instances>/<user>/<id>/.state/` |
| arsip sesi | `labs/<id>/sessions/` | `<instances>/<user>/<id>/sessions/` |
| topologi | file asli soal | `topology.clab.yaml` hasil render |
| nama lab / container | `net001` / `clab-net001-<node>` | `net001-<user>` / `clab-net001-<user>-<node>` |

Topologi hasil render sama dengan aslinya, kecuali `name` diberi akhiran user,
semua path relatif (binds, `startup-config`) jadi absolut, dengan
`.state/...` menunjuk ke state instance, dan ada blok `mgmt` (jaringan
management milik user, lihat di bawah). Golden transcript tetap milik soal
(`labs/<id>/golden/`). Nama user dibatasi `^[a-z0-9][a-z0-9-]{0,31}$`, dan `local` dicadangkan untuk install pribadi.
`<instances>` adalah `var/instances/` di mode Pribadi dan `<data_dir>/instances/`
di mode Server (`config.py`).

Tool CLI dan script memilih instance lewat env `LAB_INSTANCE` (default
`local`). `reset-lab`, `sessions.py`, `evaluate.py`, dan web UI meneruskan
kontrak env ini ke `inject.sh`/`verify.sh` (lihat `platform/labenv.sh`):
`LAB_INSTANCE`, `LAB_STATE_DIR`, `LAB_CLAB_NAME`, `LAB_TOPO`. Web UI tidak
memakai env proses untuk memilih instance: setiap request memakai instance
milik user yang login (mode Pribadi: selalu `local`).

### Jaringan management per user

Router RouterOS butuh jaringan management (SSH dari host untuk `ros.py`,
Winbox). Kalau semua instance berbagi jaringan default `clab`
(172.20.20.0/24), router siswa A bisa `/system telnet` ke router siswa B
dengan login default `admin/admin`. Karena itu render instance non-local
menambahkan:

```yaml
mgmt:
  network: plab-<user>
  ipv4-subnet: 172.20.<n>.0/24
  ipv6-subnet: 3fff:172:20:<n>::/64
  external-access: false
```

- `<n>` dialokasikan sekali per user (0–255, kecuali 20 milik jaringan
  default) dan disimpan di `<instances>/<user>/mgmt.json`, jadi semua lab milik
  user itu memakai subnet yang sama di setiap deploy. Alokasi memakai file lock
  dan melewati subnet yang sudah dipakai jaringan docker atau route host.
  Maksimal 255 user punya subnet sekaligus; `instance.release_mgmt()`
  melepasnya saat akun dihapus.
- `ipv6-subnet` wajib eksplisit: tanpa itu containerlab memberi semua jaringan
  IPv6 default yang sama, dan deploy kedua gagal.
- `external-access: false` mencegah containerlab memasang aturan ACCEPT ke
  bridge ini di chain `DOCKER-USER`, yang akan melewati isolasi antar-jaringan
  docker. Host tetap bisa menjangkau router (host ada di bridge itu).
- `containerlab destroy --cleanup` menghapus jaringan instance yang sudah tidak
  dipakai container; jaringan user lain tidak tersentuh.
- Instance `local` tidak berubah: tetap di jaringan default `clab`.

### Kapasitas (mode Server)

`platform/capacity.py` menjalankan `capacity.*` di config: perkiraan RAM per
lab (`resources.mem_mb` di problem.yaml, atau dihitung dari topologi), batas
deploy bersamaan (`max_deploys`), satu lab berjalan per user (lab lain milik
user dimatikan sebelum deploy baru), dan pembersihan lab idle
(`idle_minutes`) serta lab milik akun nonaktif. Lab yang berjalan ditemukan dari
label docker `containerlab=<nama lab>`. Mematikan satu instance:
`reset-lab --destroy-only <lab_dir>` (dengan env instance); sesi yang belum
dinilai diarsipkan dulu ke `sessions/<sesi>/` dengan `abandoned.json`.

## Login dan mode Server

Tanpa config, P-lab berjalan di mode **Pribadi**: tanpa login, satu orang,
instance `local`. Dengan `mode: server` di `/etc/p-lab/server.yaml` (atau
`LAB_CONFIG`), semua `/api/*` kecuali `/api/auth/login`, `/api/auth/logout`, dan
`/api/me` butuh login ([server](server.md)).

- **Akun** dibuat admin (`platform/p-lab-admin`), disimpan di
  `<data_dir>/p-lab.db` (`accounts.py`). Username = nama instance lab, jadi user
  hanya pernah menyentuh lab, state, dan arsipnya sendiri.
- **Sesi login** = cookie `plab_session` (HttpOnly, SameSite=Lax, Secure kalau
  lewat HTTPS), berlaku 12 jam. Middleware di `server.py` memeriksanya untuk
  semua `/api/*`; WebSocket sesi dan terminal memeriksa cookie yang sama.
- **Host yang diizinkan** (penangkal DNS rebinding): semua request HTTP, termasuk
  file web, dan kedua WebSocket ditolak (400 / close 4401) kalau header `Host`
  bukan nama yang diizinkan. Pribadi: hanya `localhost`, `127.0.0.1`, `[::1]`
  (port apa pun, jadi Vite dev di `localhost:5173` tetap jalan). Server:
  `allowed_hosts` di config ditambah tiga nama loopback tadi; kalau
  `allowed_hosts` kosong, Host apa pun diterima dan server mencatat peringatan.
  Tanpa cek ini, situs jahat yang mengarahkan domainnya ke 127.0.0.1 punya
  `Origin` = `Host` = domainnya sendiri, sehingga cek CSRF di bawah lolos.
- **CSRF**: request yang mengubah state (POST dll.) dan WebSocket ditolak kalau
  header `Origin` tidak sama dengan `Host`. Berlaku juga di mode Pribadi, karena
  di sana tidak ada cookie yang melindungi `localhost:8000` dari situs lain.
- **Login gagal dibatasi** per (IP, username) dan per IP, di memori proses. IP
  klien = alamat koneksi; `X-Forwarded-For` (dan `X-Forwarded-Proto` untuk flag
  `Secure`) hanya dipercaya dari proxy di `trusted_proxies`, dibaca dari kanan
  sampai alamat pertama yang bukan proxy tepercaya.
- **Yang terlihat tanpa login**: `GET /api/me` hanya mengirim `mode`, `style`,
  `auth`, dan `user: null`; info LLM dan kemampuan deploy baru dikirim setelah
  login.
- **Golden transcript** (jawaban expert di `golden/` milik soal) di mode Server
  hanya bisa dibuka guru/admin; siswa mendapat 404. **Provider/model LLM** saat
  menilai hanya boleh dipilih admin; user lain memakai default server.
- **Terminal dan WebSocket sesi** memeriksa ulang login secara berkala (logout,
  akun nonaktif, atau sesi kedaluwarsa memutus koneksi).
- **Kunci per instance**: penilaian (`EvalJobs`), deploy (`DeployJobs`), dan
  watcher (`Runtimes`) dikunci per instance, jadi deploy user A hanya
  menghentikan watcher A dan `reset.sh` hanya menyentuh lab `<nama>-A`. Satu
  user men-deploy satu lab dalam satu waktu.
- **Leaderboard**: Pribadi membandingkan kamu dengan golden transcript. Server
  gaya `mandiri` memeringkat semua user dengan nama; gaya `kelas` hanya
  memeringkat siswa, dan siswa melihat teman sekelas tanpa nama. Guru/admin di
  gaya `kelas` punya `GET /api/class/progress` (sesi dan skor terbaik per lab
  tiap user).

## Alur satu sesi

1. **Deploy** (`reset-lab`): siapkan instance (render topologi kalau bukan
   `local`), destroy, buat `.state/`, lalu `containerlab deploy -t <topologi
   instance>`, `verify.sh` (harus 100), dan `inject.sh` (fault +
   `ground_truth.json`). `session_id` ditulis **paling akhir**, jadi sesi baru
   dianggap ada kalau semua tahap berhasil.
2. **Bermain**: setiap command yang selesai di node ditulis oleh hook bash
   sebagai satu baris JSON (command, exit code, waktu). Di sisi host, `script`
   merekam input dan output mentah terminal.
3. **Checkpoint live**: `checkpoints.py watch` membaca event baru, mencocokkan
   `command_match`, dan menjalankan `state_check` di node yang baru menerima
   command. Hasilnya ditulis ke `checkpoints.jsonl`. Untuk lab RouterOS, watch
   juga menjalankan `guiwatch.py`: konfigurasi router (`/export terse`)
   dibandingkan berkala, dan perubahan yang tidak berasal dari terminal P-lab
   (Winbox, WebFig, API) ditulis sebagai event command dengan field `source`.
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
6. **Arsip**: `.state/` disalin ke `sessions/<sesi>/` milik instance. Halaman
   Hasil, Progress, dan Leaderboard membaca dari arsip ini.

## Isi `.state/`

Direktori state instance (`LAB_STATE_DIR`; untuk `local`: `labs/<id>/.state/`).

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
- **Terminal hanya lewat server** (`termbridge.py`, port yang sama dengan web UI).
  Setiap koneksi dicek login, Origin, dan kepemilikan instance, lalu hanya
  menjalankan `lab-shell`, yang menolak nama node di luar `[a-z0-9-]`.
  `platform/serve` (mode terminal tanpa web) masih memakai ttyd yang listen di `lo`.
- **Node lab tidak punya jaringan management** (`network-mode: none`), jadi
  node hanya bisa saling menjangkau lewat link soal. Node yang butuh management
  (router VM) ada di jaringan management milik user-nya sendiri (lihat
  Jaringan management per user).
- **Evaluator AI hanya membaca.** LLM menerima transcript dan tidak punya tool
  untuk mengeksekusi apa pun di lab.
- **Hak root containerlab** didapat lewat sudo atau mode setuid `clab_admins`
  ([instalasi](instalasi.md#deploy-lab-tanpa-sudo)). Server sendiri berjalan
  sebagai user biasa.

## Modul `platform/`

| File | Peran |
|---|---|
| `server.py` | API + WebSocket + file statis web UI |
| `termbridge.py` | terminal web: WebSocket ↔ PTY yang menjalankan `lab-shell` |
| `accounts.py`, `p-lab-admin`, `config.py`, `migrate-server` | akun & login, konfigurasi mode Pribadi/Server, migrasi |
| `instance.py`, `labenv.sh` | instance lab per user (state, nama lab, topologi render, jaringan management) + kontrak env script soal |
| `capacity.py` | batas RAM, deploy bersamaan, satu lab per user, lab idle/orphan (mode Server) |
| `reset-lab`, `sessions.py` | siklus hidup sesi: deploy, destroy (`--destroy-only`), rearm tanpa deploy, arsip |
| `lab-shell`, `lab-rc.sh`, `serve` | perekaman terminal |
| `ros.py` | shell proxy RouterOS (prompt, konteks menu, SSH, event) + `exec` untuk inject/verify/state_check |
| `checkpoints.py` | matcher checkpoint (watch live + status) |
| `guiwatch.py` | rekam perubahan RouterOS dari luar terminal (Winbox/WebFig/API) sebagai event |
| `hints.py`, `lab-hint` | hint berjenjang yang tercatat |
| `transcript.py` | event → timeline E-id, klasifikasi perubahan state per NOS |
| `scoring.py` | rumus deterministik |
| `evaluate.py`, `report.py`, `prompts/` | evaluator dan laporan |
| `llm/` | lapisan provider LLM ([README](../platform/llm/README.md)) |
| `autoplay.py` | memainkan skenario otomatis → golden transcript |
| `lablint.py`, `newlab.py`, `templates/lab/` | membuat dan memeriksa soal |
| `install-service.sh`, `setup-sudoless.sh`, `build-routeros-image.sh` | dipanggil installer |
| `_venv.py` | menjalankan ulang script CLI dengan Python `.venv` |
