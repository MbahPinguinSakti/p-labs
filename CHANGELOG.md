# Changelog

Catatan setiap penambahan dan perbaikan, terbaru di atas. Rencana, status fase, dan roadmap ada di [rencana.md](rencana.md).

Format tiap entri: **apa** yang berubah, **kenapa** (gejala/temuan), **file**, dan **verifikasi**.

---

## 2026-11-06 (8): Fitur: perubahan dari Winbox ikut direkam dan dinilai

**Kenapa**: semua perekaman lewat `ros.py shell`. Winbox/WebFig/API (service-nya aktif secara default, port 8291 terbuka di IP management) melewati proxy itu, jadi pemain Winbox dirugikan (process gate gagal) sekaligus bisa lolos dari aturan safety. User memilih mendukung Winbox, bukan memblokirnya.

### Ditambahkan
- `platform/guiwatch.py`: thread per router di dalam `checkpoints.py watch`.
  - Tiap 3 detik mengambil `/export terse` dan membandingkannya dengan snapshot sebelumnya. Selisihnya diterjemahkan jadi command RouterOS lengkap: entri yang diedit → `set [find interface=…]`, entri baru → `add`, entri hilang → `remove`, `[ find default-name=ether3 ]` → `ether3`. Akibatnya aturan NOS, safety, efficiency, dan `state_check` langsung berlaku.
  - Kalau ada command tulis dari terminal P-lab di node yang sama dalam jendela itu (+2 detik jeda), selisihnya dianggap dari terminal dan tidak dicatat dobel.
  - Login `via winbox/web/api/...` dari `/log` → event `gui_login` dan label `source`. Login lewat SSH diabaikan, karena tidak bisa dibedakan dari `ros.py`/state_check.
  - `checkpoints.py watch --no-gui` untuk mematikannya.
- Penilaian (`evaluate.py`, `scoring.waive_gate`): `rule_based.gui` berisi via, daftar perubahan, dan apakah fix dibuat dari luar terminal. Process gate **hanya** dibebaskan kalau event fix-nya sendiri berasal dari GUI. Login Winbox lalu memperbaiki di terminal tanpa diagnosis tetap kena gate.
- Prompt evaluator: bagian "Pemain memakai GUI" (aktivitas membaca tidak terekam, jangan simpulkan tanpa diagnosis, jangan beri band `sistematis`). Timeline memberi tag `[WINBOX]`.
- Web: panel **Winbox** di halaman sesi (IP:8291 per router, login, cara tunnel dari komputer lain), badge sumber di Aktivitas dan timeline Hasil, serta keterangan gate yang dibebaskan.
- Docs: `penggunaan.md` (Memakai Winbox, pengecualian gate), `arsitektur.md`.

### Batasan
- Membaca di GUI tidak terekam sama sekali, jadi checkpoint `command_match` diagnosis tidak bisa dicapai lewat Winbox.
- Waktu event GUI = waktu terdeteksi (terlambat ≤ ~5 detik), bukan waktu klik.
- Perubahan GUI dan terminal di node yang sama dalam jendela beberapa detik → perubahan GUI-nya tidak tercatat (sengaja dipilih supaya tidak dobel).

### Verifikasi
- `platform/tests/test_guiwatch.py` (16 test): diff export (edit/add/remove/kutipan/interface/singleton/disable), kecocokan dengan NOS dan safety net-002, deteksi command tulis terminal, baseline login, serta sesi net-002 sintetis (fix lewat winbox → gate dibebaskan; fix di terminal → gate tetap). Seluruh suite: 92 test OK. `tsc` + `npm run build` OK, golden net-001 `--rules-only` semua lolos.
- **Belum diuji di router sungguhan**: router net-002 mati sejak mesin reboot, dan deploy ulang butuh `sudo`.

## 2026-11-06 (7): Perbaikan: inject net-002 gagal "Fault tidak efektif"

**Gejala**: `reset.sh` net-002 berhenti dengan `Fault tidak efektif: host-b masih terjangkau setelah inject.`, plus `RuntimeWarning: Unexpected value in sys.prefix`.

**Penyebab**:
- Fault sebenarnya sudah terpasang (r2 ether3 = `/25`, beberapa detik kemudian ping dibalas `Net Unreachable`). Rute connected di RouterOS baru berubah sesaat *setelah* `/ip address set` kembali. `ping -c 2` langsung dijalankan dan cukup satu balasan untuk exit 0, jadi pengecekan kalah balapan (race).
- Warning muncul karena Python venv dipanggil lewat path relatif yang belum dinormalisasi (`labs/net-002/../../.venv/bin/python`). Python membandingkannya dengan `sys.prefix` yang sudah dinormalisasi.

### Diperbaiki
- `labs/net-002/inject.sh`: cek putus diulang hingga 10× dengan jeda 1 detik (pola yang sama dengan net-003).
- `labs/net-00{2,3}/{inject,verify}.sh`: `PY` memakai path absolut `$(cd ../.. && pwd)/.venv/bin/python`. Sengaja tidak memakai `realpath`, karena realpath mengikuti symlink ke `/usr/bin/python3` dan keluar dari venv.

### Verifikasi
- r2 dikembalikan ke `/24` (host-b terjangkau), lalu `./inject.sh` → `Fault injected.`, exit 0, tanpa warning.

## 2026-11-06 (6): Perbaikan: build image RouterOS di VM Ubuntu

**Gejala** (laporan user, VM Ubuntu):
- `build-routeros-image.sh` gagal `unknown flag: --platform`, lalu `No such image: vrnetlab/mikrotik_routeros:7.20.4`;
- muncul peringatan `/dev/kvm tidak bisa diakses`.

**Penyebab**:
- Makefile vrnetlab memanggil `docker buildx build --platform`. Paket `docker.io` di Ubuntu tidak menyertakan plugin buildx, sehingga docker membaca `buildx` sebagai perintah tak dikenal.
- vrnetlab versi baru men-tag image dengan akhiran arsitektur (`7.20.4-amd64`), padahal lab memakai `7.20.4`. Jadi build yang berhasil pun akan gagal di pengecekan akhir.
- `/dev/kvm` tidak ada karena P-lab berjalan di VM tanpa nested virtualization.

### Diperbaiki
- `platform/build-routeros-image.sh`:
  - mengecek `docker buildx version` sebelum mulai, dan menampilkan nama paket per distro kalau belum ada;
  - setelah build, kalau hanya ada tag ber-akhiran (`<versi>-*`), image di-tag ulang ke `<versi>`;
  - peringatan KVM dibedakan: tidak ada di VM (nested virtualization), tidak ada di mesin fisik (BIOS), atau ada tapi tanpa izin (grup kvm).
- `install.sh --check`: diagnosis KVM yang sama.
- `docs/instalasi.md`: syarat buildx dan bagian baru "P-lab di dalam VM" (cara mengaktifkan nested virtualization per hypervisor).

### Verifikasi
- `bash -n` lulus untuk kedua script.
- Logika tag ulang dites dengan image dummy (`plabtest/ros:9.9.9-amd64` → `:9.9.9`, lalu dihapus).
- Build CHR sungguhan belum dites, baik di sini maupun di VM.

---

## 2026-11-06 (5): Perbaikan: "Penilaian gagal: ground_truth.json tidak ada"

**Gejala** (laporan user, VM Ubuntu): tombol nilai menampilkan `FileNotFoundError: .state/ground_truth.json`.

**Penyebab**: `session_id` ditulis **sebelum** fault dipasang, baik di `reset-lab` (sebelum `containerlab deploy`) maupun di `sessions.rearm` (sebelum `inject.sh`). Kalau deploy, verify, atau inject gagal, `.state/` tetap berisi `session_id` tanpa `ground_truth.json`. Server lalu menganggapnya sesi aktif: terminal terbuka, command direkam, dan baru gagal saat dinilai. Di Ubuntu kemungkinan besar deploy atau verify gagal, karena lab-nya baru pertama kali dipasang di sana.

### Diperbaiki
- `reset-lab` dan `sessions.rearm` menulis `session_id` **terakhir**, setelah `inject.sh` berhasil dan `ground_truth.json` terbukti ada. Kalau file itu tidak ada, keduanya gagal dengan pesan jelas.
- `server.py`: `armed(lab)` mensyaratkan `session_id` dan `ground_truth.json`. Fungsi ini dipakai di `live_state`, `/start`, dan `/evaluate`, jadi state rusak sisa versi lama tampil sebagai "belum ada sesi" dan bisa langsung di-deploy atau dimulai ulang.
- `evaluate.py`: kalau ground truth tidak ada, pesannya menyuruh memulai sesi baru, bukan menampilkan traceback.
- `docs/arsitektur.md`: urutan deploy diperbarui.

### Verifikasi
- `TestUnarmedSession`: sesi tanpa ground truth tidak tampil aktif, dan `/evaluate` menjawab 409.
- Semua test lulus (76 OK, 2 dilewati).
- `bash -n platform/reset-lab` lulus.
- Deploy sungguhan belum diulang di sini (butuh sudo).

---

## 2026-11-06 (4): Perbaikan: installer gagal `Permission denied` (Ubuntu VM)

**Gejala** (laporan user, VM Ubuntu):
- `pip` mendapat `Permission denied: .venv/pyvenv.cfg`;
- `npm ci` mendapat `EACCES rmdir web/node_modules/.bin`;
- build web gagal dengan `Cannot find native binding` (rolldown).

**Penyebab**:
- `.venv` dan `node_modules` milik root, kemungkinan karena run sebelumnya memakai `sudo ./install.sh` (atau `sudo npm`). Installer sendiri tidak membuat file sebagai root.
- Error rolldown hanya efek samping: `npm ci` berhenti di tengah, jadi binding native-nya belum terpasang.
- Installer tetap lanjut setelah langkah yang gagal. `cmd && ok "..."` tidak memicu `set -e`, sehingga build web tetap dijalankan dengan `node_modules` yang rusak.

### Diperbaiki
- `install.sh`:
  - menolak berjalan sebagai root, karena sudo dipanggil sendiri per langkah;
  - memeriksa kepemilikan `.venv`, `web/node_modules`, `web/dist`, dan `~/.npm`, lalu menawarkan `sudo chown -R $USER:`. Kalau ditolak, installer berhenti dengan perintah perbaikannya. `--check` ikut melaporkannya;
  - kegagalan pip, `npm ci`, atau build web sekarang menghentikan installer (`die`) dan tidak lanjut diam-diam.
- `docs/instalasi.md`: satu baris baru di tabel Masalah umum.

### Verifikasi
- `bash -n` lulus.
- `./install.sh --check` di mesin ini bersih.
- Simulasi file milik user lain (`USER=nobody`) terdeteksi di `--check` maupun run biasa. Installer berhenti dengan perintah `chown`.
- Belum dites di VM Ubuntu.

---

## 2026-11-06 (3): Perbaikan: terminal web menampilkan `login:` di Ubuntu

**Gejala** (laporan user, Ubuntu): terminal di halaman sesi menampilkan `[user] login:` dan tidak bisa diketik.

**Penyebab**: paket `ttyd` di Debian/Ubuntu memasang service systemd `ttyd` yang menjalankan `login` di port 7681 tanpa `-W` (read-only). Port itu sama dengan port default kita. `Runtime.ensure` memakai ulang **proses apa pun** yang membuka 7681, karena dianggap ttyd dari `platform/serve`. Akibatnya iframe tersambung ke ttyd milik sistem.

### Diperbaiki
- `server.py`:
  - `lab_ttyd_on(port, dir)` membaca `/proc/*/cmdline`. ttyd luar hanya dipakai ulang kalau ia menjalankan `lab-shell` untuk direktori lab yang sama;
  - selain itu server memilih port kosong berikutnya (`free_port`, 7682+). Frontend sudah memakai `ttyd_port` dari API, jadi tidak perlu diubah;
  - server juga menunggu sampai ttyd listen (maks. 2 detik) sebelum menjawab, supaya iframe tidak memuat port yang masih kosong.
- `install.sh`: kalau service `ttyd` bawaan aktif, installer menawarkan `systemctl disable --now ttyd`. `--check` melaporkannya.
- `platform/serve`: gagal dengan pesan jelas kalau port-nya sudah dipakai.
- `docs/instalasi.md`: baris baru di tabel masalah umum.

### Verifikasi
- `tests/test_server.py` +2 (dengan ttyd asli, dilewati kalau ttyd tidak ada):
  - `ttyd ... login` di sebuah port tidak dipakai ulang, dan `free_port` memilih port lain;
  - ttyd `lab-shell` untuk lab yang sama dipakai ulang, sedangkan untuk lab lain tidak.
  - Total 74 OK, 2 skipped.
- End-to-end di service yang berjalan: dengan `ttyd -i lo -p 7681 login` aktif (meniru Ubuntu), `POST /api/labs/net-001/runtime` menjawab `ttyd_port: 7682`, dan ttyd baru menjalankan lab-shell.
- **Belum diuji di Ubuntu sungguhan.** Penyebabnya disimpulkan dari gejala, belum dicek langsung di mesin itu.

---

## 2026-11-06 (2): Dua soal MikroTik RouterOS (net-002, net-003) + dukungan RouterOS di platform

**Kenapa** (permintaan user): soal baru dengan router MikroTik. RouterOS tidak punya bash, jadi perekam `lab-rc.sh` tidak bisa dipakai, dan tidak ada image container x86 resmi. Perlu jalur rekam dan jalur image sendiri.

### Ditambahkan
- **`labs/net-002` Subnetting Dasar** (beginner). host-a, r1, r2, host-b dengan routing statis. Fault: prefix LAN-B di r2 ether3 dipersempit menjadi /25, sehingga server .130 jatuh di luar subnet.
  - Jalan pintas yang dinilai 50: mengubah IP server, atau menambal dengan rute /32.
- **`labs/net-003` OSPF Neighbor Stuck** (advanced). Tiga router dengan OSPF area 0. Fault: MTU r2 ether3 diturunkan ke 1400, lalu interface di-flap, sehingga adjacency r2–r3 macet di ExStart/Exchange.
  - Jalan pintas yang dinilai 50: menurunkan MTU di sisi r3, atau memasang rute statis. verify memeriksa MTU, adjacency Full, dan tidak adanya rute statis.
  - Keduanya lengkap dengan konfigurasi `.rsc` per router, checkpoint, safety, hint, `design.links`, autoplay expert, dan README berisi skenario uji manual.
- **`platform/ros.py`**:
  - `shell`: proxy CLI RouterOS di host, dengan prompt `[admin@r2] /ip address>`, konteks menu, `..`/`/`, Tab completion, dan scripting yang diteruskan apa adanya. `ping`/`traceroute`/`monitor` dibatasi otomatis. Command dikirim lewat SSH (paramiko), lalu dicatat ke `events/<node>.jsonl` dalam **bentuk lengkap** beserta output-nya;
  - exit code ditentukan dari pesan error RouterOS;
  - `exec` untuk inject/verify/state_check.
- **`platform/nos/routeros.yaml`** + dukungan `include:` di `NosRules`: aturan RouterOS digabung dengan aturan host Linux.
- **`platform/build-routeros-image.sh`**: vrnetlab + CHR resmi → `vrnetlab/mikrotik_routeros:<versi>`. Versi default diambil dari topologi lab.
- `deploy.ready_timeout` di `problem.yaml`: `reset-lab` menunggu healthcheck container, lalu mengulang verify sampai sehat.
- Web/API:
  - `missing_images` di detail lab. Selama image RouterOS belum dibangun, Deploy dinonaktifkan, perintah build ditampilkan, dan endpoint deploy menolak dengan 409;
  - diagram menampilkan nama interface RouterOS (eth1 → ether2);
  - perkiraan waktu deploy 2–4 menit untuk lab RouterOS;
  - contekan RouterOS di jalur Belajar Networking;
  - "Subnetting Dasar" dan "OSPF Neighbor Stuck" keluar dari daftar "segera hadir".
- Installer:
  - tahap 4 menawarkan build image RouterOS, bukan `docker pull`, yang pasti gagal untuk image itu;
  - `--check` melaporkan image RouterOS dan KVM.
- Dokumentasi:
  - `docs/instalasi.md#lab-mikrotik-routeros`;
  - shell RouterOS di `penggunaan.md`;
  - bagian "Lab MikroTik RouterOS" di `membuat-lab.md`;
  - diagram dan tabel modul di `arsitektur.md`.

### Diubah
- `lab-shell` memilih shell berdasarkan kind node. `checkpoints.Lab` mengetahui kind tiap node (`run_on` lewat SSH untuk RouterOS).
- `autoplay.py` mengenali prompt shell RouterOS.
- `lablint`:
  - safety dengan `key` di level rule dianggap valid (memang didukung `scoring.py`);
  - `network-mode` dicek per node Linux, termasuk lewat `kinds`;
  - file `startup-config` dicek keberadaannya.
- `DeployJobs` menutup pipe `reset.sh`, sehingga ResourceWarning hilang.
- `paramiko` masuk `requirements.txt`.

### Verifikasi
- `tests/test_ros.py` (+15):
  - normalisasi command (absolut, navigasi menu, relatif, pembatasan ping/monitor, scripting);
  - deteksi error;
  - aturan NOS RouterOS + include Linux;
  - lint kedua lab, kind node, nama interface di topologi web, regex diagnose cocok/tidak cocok;
  - format event shell sama dengan lab-rc.
  - Total 72 test OK, 2 skipped.
- `lab-lint` net-001..003 OK. API menampilkan ketiga lab dan `missing_images` untuk net-003. Semua link docs valid.
- **Belum diuji di RouterOS sungguhan.** Build image ditolak oleh permission mode, karena menjalankan kode yang diunduh (vrnetlab + CHR). Yang perlu dipastikan saat pertama deploy:
  - SSH admin/admin ke container;
  - teks pesan error RouterOS cocok dengan `ERROR_RX`;
  - `.rsc` terpasang saat boot;
  - RouterOS v7 benar-benar menahan adjacency di ExStart saat MTU berbeda (`inject.sh` net-003 gagal dengan pesan jelas kalau tidak);
  - semua baris tabel uji manual di README kedua lab.

---

## 2026-11-06 (1): Catatan internal tidak ikut didistribusikan, README menaut ke docs

**Kenapa** (arahan user): `rencana.md`, `CHANGELOG.md`, dan `.claude/` adalah catatan pengembangan, bukan dokumentasi pengguna.

### Diubah
- `.gitignore`: `rencana.md`, `CHANGELOG.md`, `.claude/`. File-filenya tetap ada di mesin pengembang.
- Rujukan ke `rencana.md`/`CHANGELOG.md` dihapus atau dialihkan ke `docs/`, yaitu di README, `docs/membuat-lab.md`, `platform/scoring.py`, `web/src/pages/Leaderboard.tsx`, dan golden `expected.yaml` net-001.
- `README.md` sekarang menaut ke bagian-bagian docs di tiga tempat:
  - daftar fitur (skor, evaluator AI, hint, membuat lab);
  - mulai cepat (installer, sudo-less, masalah umum, sesi pertama);
  - struktur folder, yang kini berupa tabel dengan kolom dokumentasi.

- `design/` dipindah user ke luar repo (`project_lab/design/`). Akibatnya build web gagal, karena `global.css` meng-import `../../../design/tokens.css`. Token sekarang disalin ke `web/src/styles/tokens.css`, sama seperti website yang juga punya salinan sendiri, sehingga repo bisa di-build tanpa folder desain. Rujukan `design/` di README dan `server.py` ikut diperbarui.

### Verifikasi
- Semua link relatif dan anchor di README + `docs/` dicek dengan script: 0 rusak.
- `npm run build` berhasil lagi.

---

## 2026-11-05 (2): Distribusi: installer, template soal, dokumentasi

**Kenapa**: tujuan project berubah. P-lab harus mudah dipasang orang lain dan mudah ditambah soal baru. Sebelumnya setup hanya terdokumentasi lewat catatan di mesin pembuatnya, dan membuat soal baru berarti menyalin net-001 lalu menebak bagian mana yang wajib.

### Ditambahkan
- **`install.sh`** (root). Enam tahap, aman dijalankan berulang (juga untuk update):
  1. dependensi sistem (docker, containerlab, ttyd, Python ≥ 3.10 + venv, Node ≥ 20.19, util-linux) untuk Arch, Debian/Ubuntu, dan Fedora, plus grup docker;
  2. `.venv`, dibuat ulang otomatis kalau folder project dipindah;
  3. `npm ci` + build web;
  4. `docker pull` semua image di `labs/*/*.clab.yaml`, lalu `lab-lint` semua lab;
  5. service systemd user;
  6. deploy sudo-less (opsional, dengan penjelasan konsekuensi).
  - Opsi: `--check`, `--yes`, `--no-deps`, `--no-service`, `--sudoless`/`--no-sudoless`.
  - Semua aksi sudo ditanyakan dulu.
- **`platform/reset-lab`**: logika reset generik, dibaca dari `problem.yaml` (`lab_topology`, `fault_injection.script`, `goal_state.verify_script`). `labs/net-001/reset.sh` sekarang satu baris.
- **`platform/templates/lab/`**: soal kecil yang langsung bisa dimainkan (2 host + 1 bridge, fault "port dilepas dari bridge"), lengkap dengan checkpoint, safety, hint, `design.links`, autoplay expert, dan komentar kontrak di setiap file.
- **`platform/new-lab`** (`newlab.py`): scaffold dari template. Placeholder `__ID__`/`__TITLE__`/`__CLAB_NAME__` sengaja berbeda dari `{{parameter}}` soal dan format docker `{{.State.Running}}`.
- **`platform/lab-lint`** (`lablint.py`): validasi statis, meliputi:
  - field wajib dan `{{parameter}}` yang tidak didefinisikan;
  - regex (dicek setelah parameter diisi);
  - script executable dan bind perekaman;
  - node checkpoint ada di topologi, jumlah bobot = 1, `process_gate` merujuk checkpoint yang ada;
  - level hint berurutan, `design.links` cocok dengan endpoints;
  - nilai parameter non-node yang tersebut di brief (potensi bocor).
- **`platform/_venv.py`**: script CLI (`lab-hint`, `evaluate.py`, `autoplay.py`, `checkpoints.py`, ...) otomatis menjalankan ulang dirinya dengan Python `.venv`. Alasannya: shebang `python3` sistem belum tentu punya PyYAML di distro lain.
- **Dokumentasi**:
  - `README.md` (root);
  - `docs/instalasi.md`: kebutuhan, tahap installer, sudo-less, LLM, service, update, uninstall, tabel masalah umum;
  - `docs/penggunaan.md`: alur sesi di web, cara skor dihitung, membaca hasil, mode terminal, lokasi data;
  - `docs/membuat-lab.md`: langkah merancang soal, kontrak tiap file, referensi `problem.yaml`, menguji soal sampai golden + `check-all`, checklist anti-bocor;
  - `docs/arsitektur.md`.
- `.gitignore` root: `.venv`, build web, `.state/`, `clab-*`, `sessions/`.

### Diubah
- `platform/setup-sudoless.sh` mencari containerlab lewat `command -v` (installer resmi di Debian/Fedora tidak selalu memakai path yang sama).
- `platform/serve` memakai Python venv.
- `platform/install-service.sh` me-restart service (bukan hanya `enable --now`), supaya update kode ikut terpakai.
- `evaluate.py`, `lablint.py`, `newlab.py` dijadikan executable.
- `rencana.md`: tujuan distribusi di bagian 1, status di bagian 11, langkah 5 di bagian 12.

### Verifikasi
- `tests/test_lablint.py` (+7):
  - net-001 bersih;
  - scaffold bersih dan semua placeholder terisi (format docker tetap utuh);
  - id duplikat ditolak;
  - error terdeteksi untuk parameter tak terdefinisi, regex rusak + bobot ≠ 1, node/link tak dikenal, dan bind events hilang.
  - Total 57 test OK, 2 skipped.
- `./install.sh --check` dan `./install.sh --yes --no-sudoless` jalan penuh di CachyOS; web UI merespons 200 setelah service di-restart.
- `lab-lint` net-001 dan lab hasil scaffold: OK. Semua link relatif di dokumentasi valid.
- **Belum diuji**:
  - deploy template sungguhan (butuh containerlab dengan sudo);
  - installer di Debian/Ubuntu/Fedora yang bersih.

---

## 2026-11-05 (1): Web UI tanpa terminal: service systemd + deploy lab dari web

**Kenapa**: sebelumnya user harus membuka terminal, menjalankan `platform/web`, lalu menjalankan `./reset.sh` (butuh password sudo) setiap kali lab mati atau rusak.

### Ditambahkan
- **`platform/install-service.sh`** (tanpa sudo):
  - membuat service systemd user `p-lab` yang menjalankan `platform/web` saat login, dengan `Restart=on-failure`;
  - menambahkan ikon **P-lab** di menu aplikasi (start service, lalu buka `localhost:8000`);
  - membuat `~/.config/p-lab/web.env` (chmod 600) berisi provider LLM dan `LAB_LLM_API_KEY_FILE`;
  - `--uninstall` membatalkan semuanya.
- **`platform/web`** membaca `LAB_LLM_API_KEY_FILE`, supaya key tidak pernah ditulis di file unit atau env.
- **`platform/setup-sudoless.sh`** (sekali, dengan sudo):
  - mengaktifkan mode sudo-less bawaan containerlab: binary setuid `root:clab_admins` 4750, dan user masuk grup `clab_admins`;
  - memasang pacman hook supaya izin itu dipasang ulang setiap `containerlab-bin` di-update;
  - `--undo` mengembalikannya.
  - Konsekuensi: anggota `clab_admins` praktis setara root lewat containerlab, sama seperti grup docker.
- **Server**:
  - `deploy_support()` mendeteksi apakah containerlab bisa jalan tanpa password: setuid dan bisa dieksekusi, atau `sudo -n -l`. Hasilnya dikirim di `/api/me`;
  - `POST /api/labs/<id>/deploy` menjalankan `reset.sh` di background (`DeployJobs`). Watcher dan ttyd dihentikan dulu, dan tahapnya dikirim lewat WebSocket;
  - selama deploy, `live_state` melaporkan "belum ada sesi" supaya UI tidak masuk ke sesi yang node-nya belum hidup;
  - Mulai sesi ditolak selama deploy berjalan.
- **UI**:
  - **Deploy & mulai** saat lab belum berjalan;
  - **Deploy ulang lab** saat "Mulai sesi" ditolak karena lab rusak;
  - **Reset lab** (dengan konfirmasi) di sesi berjalan;
  - progres 4 tahap dengan timer;
  - tanpa setup sudo-less, UI tetap menampilkan `./reset.sh` beserta alasannya.

### Diubah
- **`labs/net-001/reset.sh`**:
  - memakai `containerlab` langsung kalau binary-nya setuid;
  - kalau tidak, memakai `sudo` di terminal atau `sudo -n` tanpa terminal (gagal cepat, bukan menunggu password);
  - mencetak penanda tahap `==> `.
- Error deploy hanya menampilkan 6 baris terakhir log, dan tidak menampilkan apa pun kalau gagal di tahap inject, karena output inject bisa menyebut lokasi fault.

### Verifikasi
- `tests/test_server.py` +4 test, memakai `reset.sh` palsu: tahap dan ANSI dibuang, tail error tampil, output inject disembunyikan, endpoint menolak tanpa dukungan sudo-less. Total 50 test OK, 2 skipped.
- Service aktif (`systemctl --user is-active p-lab`). `/api/me` melaporkan LLM siap (key dari file) dan deploy belum tersedia sampai setup sudo-less dijalankan.

---

## 2026-11-04 (1): Fase 3 bagian 1: web UI (FastAPI + Vite/React)

### Ditambahkan
- **`platform/server.py`** (FastAPI, satu service lokal) + **`platform/web`** (launcher: build frontend kalau perlu, lalu `http://localhost:8000`). Server:
  - membaca katalog soal dari `labs/*/problem.yaml`;
  - menjalankan **ttyd + checkpoint watcher** untuk sesi aktif, dan menghentikannya bersama server (ttyd dari `platform/serve` yang sudah jalan tetap dipakai);
  - mendorong state sesi lewat **WebSocket** `/api/labs/<id>/ws`: checkpoint, aktivitas E/H-id, hint, dan status penilaian. Dikirim hanya saat file di `.state/` berubah;
  - **Selesai & nilai** di background: `verify.sh`, lalu `evaluate()` (dengan atau tanpa AI), lalu arsip ke `labs/<id>/sessions/<sesi>/`;
  - **Mulai sesi baru tanpa sudo** (`sessions.rearm`) kalau lab sehat; kalau tidak, UI menampilkan perintah `./reset.sh`.
- **Yang tidak pernah dikirim ke browser**: ground truth, parameter soal, definisi checkpoint, teks hint yang belum dibuka, serta nama dan bukti checkpoint `hidden`. Semuanya dikunci oleh `tests/test_server.py`.
- **`web/`** (Vite + React + TypeScript, react-router). Halaman sesuai desain Figma:
  - **Home**: aksi cepat, lab unggulan dengan topologi asli, stat, dan grid lab.
  - **Labs**: filter, pencarian, banner sesi berjalan.
  - **Sesi Lab**: tiket dari `brief.md`, checkpoint live, hint berpenalti, terminal per node (iframe ttyd, shell tetap hidup saat pindah tab), topologi yang bisa diklik untuk membuka terminal, aktivitas, dan timer.
  - **Hasil Evaluasi**: skor, process gate, momen kunci dengan command-nya, checkpoint (sekarang terungkap semua), feedback, pelanggaran safety, dan timeline lengkap beserta output.
  - **Progress**: points, chart methodology, rata-rata per dimensi, riwayat.
  - **Leaderboard**.
  - **Belajar**: 3 jalur, dengan modul yang sudah dibaca disimpan di localStorage.
- **Data asli + placeholder jujur** (keputusan user):
  - lab yang belum ada soalnya tampil "segera hadir" (`web/src/lib/catalog.ts`);
  - Leaderboard mode lokal membandingkan kamu dengan golden transcript;
  - Points = jumlah skor akhir terbaik per lab, jadi mengulang lab tidak menambah poin.
- **Token dari satu sumber**: `web/src/styles/global.css` meng-import `design/tokens.css`. Font Inter dan JetBrains Mono dibundel lokal (@fontsource, tanpa CDN). Tema xterm di ttyd mengikuti token.
- **`problem.yaml`**:
  - `ui` (summary, ticket);
  - `label` dan `hidden` per checkpoint (`locate_fault` disembunyikan selama sesi karena membocorkan lokasi fault);
  - `design.links` berisi label link topologi, yaitu dokumentasi desain, bukan state.
- **`brief.md`**: penanda `<!-- cli` memisahkan instruksi terminal, yang disembunyikan di web.
- **`platform/hints.py`** (logika `lab-hint`, dipakai juga oleh server) dan **`platform/sessions.py`** (`verify`, `rearm`, `archive`). `autoplay.py` dan `lab-hint` memakai keduanya, tanpa perubahan perilaku.
- `platform/requirements.txt`.

### Diperbaiki
- **Pindah direktori** ke `~/Projects/project_lab/p-lab`:
  - `.venv` dibuat ulang, karena shebang pip dan lainnya masih menunjuk `~/Projects/lab`;
  - path memory di `.claude/rules/memory.md` diperbarui;
  - header file `.timing` golden lama masih menyebut path lama; ini hanya metadata `script` dan tidak dipakai.

### Verifikasi
- **Alur penuh lewat API** di salinan sementara `labs/` (`LAB_LABS_DIR`), dari golden jalan pintas sebagai sesi aktif:
  - halaman Sesi Lab menampilkan ttyd yang benar-benar tersambung ke container (prompt `host-a:~#`);
  - penilaian tanpa AI: arsip dibuat, methodology dan skor akhir kosong;
  - penilaian dengan AI (9router, Sonnet 4.6): 55 detik, schema ok, skor 40.0;
  - Progress dan Hasil Evaluasi terisi dari arsip itu.
- Screenshot headless (Chromium/Playwright) semua halaman pada 1440px, dicocokkan dengan PNG di `design/`. Dua temuan sudah diperbaiki:
  - iframe ttyd dicat putih karena `color-scheme` induk dark;
  - @fontsource-variable mendaftarkan nama "Inter Variable", bukan "Inter".
- Unit test: 46 lolos, 2 dilewati (baru: `test_server.py`, 9 test).
- **Belum teruji di lab hidup**: container net-001 sedang tanpa `br0` dan veth (container ter-restart), jadi sesi baru butuh `./reset.sh` (sudo).

### Belum (sisa Fase 3)
- Deteksi idle/stuck dan saran hint otomatis.
- Peringatan aksi destruktif real-time lewat WebSocket.

---

## 2026-11-03 (8): Fase 2 selesai

### Ditambahkan
- **`platform/lab-hint <problem_dir> [level]`**: membuka hint berjenjang (level harus berurutan), mencatat event `hint` ke `.state/events/host.jsonl`, dan menampilkan teks hint beserta penaltinya. Membuka ulang hint yang sama tidak menambah penalti. Sebelumnya penalti hint sudah ada di rumus, tapi tidak ada cara meminta hint. Ditambahkan juga ke `brief.md`.
- **Hint di timeline evaluator** dengan ID `H<n>`, terpisah dari `E<n>` supaya rujukan bukti di golden lama tidak bergeser. Teks hint yang dibuka ikut masuk prompt, dan `evaluator-system.md` menegaskan bahwa penalti sudah dihitung, sehingga yang dinilai adalah tindak lanjut pemain.
- **Golden ke-4 `20261103-023553` "jalan pintas"** (`autoplay/jalan-pintas.yaml`): diagnosis benar, hint 1, lalu `ip link set br0 type bridge vlan_filtering 0`. Golden pertama yang menguji pelanggaran safety major, correctness 50 dari fix yang merusak desain, penalti hint, dan `apply_fix`/`verify_fix` yang tidak tercapai walau ping berhasil.
- **`evaluate.py check-all <problem_dir>`**: semua golden satu soal, lalu ringkasan urutan skor akhir.
- **`platform/tests/test_golden.py`**: bagian deterministik semua golden (`labs/*/golden/*/expected.yaml`) masuk unit test, sekaligus memastikan mode rules-only tidak menulis apa pun ke folder golden.
- `expected.yaml`: key `hint_levels`. Autoplay: langkah `{hint: n}` dan `--capture-only`.

### Diperbaiki
- **`check --rules-only` menimpa `evaluation.json` golden** dengan hasil tanpa LLM (dan menulis `evaluator_prompt.md`). Logikanya dipindah ke `golden_checks()`, yang tidak menulis apa pun dalam mode rules-only.
- **Backend Anthropic melempar `TypeError` mentah** kalau tidak ada kredensial sama sekali. Sekarang hasilnya `LLMError("Kredensial anthropic belum diset ...")`. Ketahuan karena `python3` di shell ternyata memakai `.venv` user yang berisi SDK `anthropic`.

### Diubah
- Keputusan user: **pelanggaran safety major tidak membatasi skor akhir** (dicatat di `rencana.md` bagian 4 dan `expected.yaml` golden jalan pintas).

### Verifikasi
- **Alur live** `evaluate.py run . --provider 9router --repeat 3` pada sesi jalan pintas yang masih berjalan: `verify.sh` dipanggil langsung (correctness 50), hint terbaca, methodology 45/45/45, skor 55.0.
- **`check-all . --provider 9router --repeat 3`** (Sonnet 4.6): expert 98.0 (16/16), jalan pintas 56.2 (17/17), trial-and-error 38.0 (17/17), nyontek 12.0 (16/16). Total 66/66, spread 0 di setiap golden, tanpa warning dan tanpa retry schema. Setelah prompt diberi bagian hint, methodology trial-and-error bergeser dari 42 ke 45 (masih dalam rentang 35–65).
- **ttyd teruji ujung ke ujung** (sisa Fase 1): `serve . 7699` menyajikan HTTP 200; klien WebSocket (protokol `tty`) menerima prompt `sw1`, menjalankan `echo ttyd-$((40+2))` (output `ttyd-42`), event tercatat dengan sesi yang benar, dan rekaman tty dibuat.
- Unit test: 35 lolos, 2 dilewati (termasuk `test_golden` untuk 4 golden).

---

## 2026-11-03 (7): Revisi desain: Home, sidebar, letak hasil evaluasi, halaman Belajar

### Diubah
- **Home**: judul hero dari Triodion ke text style **Display** (Inter). Placeholder diganti instance komponen: Sidebar, Account, Tab, Chip, Button, Stat, Lab card, Topology node, Avatar, dan ikon aksi cepat. Warna mentah yang nilainya persis sama dengan token diikat ke variabel (17 paint), dan teks Inter tanpa style diberi text style yang cocok persis (13 teks). Label "My rank" menjadi "Peringkat kamu".
- **Aksi cepat Home**: Terminal, Topologi, Hint menjadi **Lanjutkan, Materi, Leaderboard**. Ketiga alat lama kini hanya hidup di dalam Sesi Lab.
- **Sidebar** (komponen, berlaku di semua halaman): grup ALAT (Terminal, Topologi) dihapus, Leaderboard pindah ke menu utama, dan ada bagian baru **SESI AKTIF** berisi komponen *Session card* (Default/Active: judul lab, progres checkpoint, timer). Di halaman Sesi Lab, kartu ini yang aktif.
- **Hasil Evaluasi dipindah dari Progress ke hierarki lab**: Labs / VLAN Trunk Misconfiguration / Sesi 19 Okt 2026 / Hasil (breadcrumb, nav Labs aktif). Alasannya, hasil evaluasi milik satu sesi pada satu lab, bukan rangkuman kemajuan. Halaman ini bisa dibuka dari tiga tempat: otomatis setelah "Selesai & nilai", kartu lab berstatus "Selesai · skor", dan baris riwayat di Progress (sekarang ada panah dan petunjuk "klik baris").
- **Komponen Button** memeluk lebar teks. Sebelumnya lebarnya tetap 160px sehingga label panjang terpotong.

### Ditambahkan
- **Halaman Belajar: Networking, Cybersecurity, Problem Solving.** Tiap halaman berisi pengantar jalur dengan progres dan tombol lanjut, 5 modul (komponen *Module card* Done/Current/Upcoming) dengan materi 2–3 kalimat yang tertaut ke satu lab, dan panel samping:
  - Networking: contekan perintah Linux, plus **padanan perintah Cisco IOS** (sebagian jawaban untuk kekurangan 10.2: pemain yang terbiasa dengan NOS tertentu).
  - Cybersecurity: contekan perintah dan aturan scope (pelanggaran = safety).
  - Problem Solving: metode yang dinilai evaluator, cara skor dihitung (bobot net-001), dan process gate.
- Komponen *Command row* (perintah mono + penjelasan).

### Verifikasi
- Audit 9 halaman: semua teks Inter memakai text style. Geist Mono hanya di terminal dan perintah. Satu-satunya warna yang tidak diikat token adalah garis link topologi `#2F6B52` (hex dari design rules, belum ada variabelnya).

---

## 2026-11-03 (6): Desain web UI Fase 3 di Figma

File Figma `project_lab` (B6VM1c2wHX7Fi3ldMe36XR), mengikuti frame "Design Rules - Labs Belajar" dan halaman Home buatan user.

### Ditambahkan
- **Frame "Komponen - Labs Belajar"**: 19 ikon SVG (24px, garis 2px), Nav item (Default/Active, prop Label + Icon swap), Nav group heading, Tab, Chip (Accent/Gold/Ember/Neutral), Button (Primary/Secondary), Avatar, Account, Sidebar, Lab card, Stat (Text/Gold/Accent), Checkpoint row (Done/Pending/AI), Moment row (Good/Issue), Leaderboard row (Self No/Yes), Topology node (Host/Switch/Router/Firewall). Semua warna diikat ke variabel Tokens, semua teks ke text style.
- **5 halaman 1440×1040** (memakai komponen di atas):
  - **Labs**: filter kategori + pencarian, kartu "lanjutkan sesi" dengan progres checkpoint, grid 8 lab.
  - **Sesi Lab**: tiket + tabel alamat, panel checkpoint, hint dengan penalti, terminal per node (tab host-a…host-b, status rekaman), topologi net-001, aktivitas event terbaru.
  - **Hasil Evaluasi**: data asli evaluasi Sonnet atas golden `20261019-234339` (skor 36.8, 4 dimensi + bobot, catatan process gate, 5 momen kunci dengan ID event, feedback, 2 pelanggaran safety).
  - **Progress**: points/lab/rata-rata methodology, grafik methodology per sesi (satu seri, sesi terakhir disorot), rata-rata per dimensi, riwayat sesi.
  - **Leaderboard**: tab periode, podium 3 besar, peringkat 4–9, baris "kamu" (#212) disorot.

### Keputusan desain
- **Checkpoint yang tercapai tidak menyebut nama atau lokasinya selama sesi** ("Checkpoint tersembunyi · detail setelah sesi"). Kalau panel menampilkan "lokasi fault: sw2 ✓", panel itu sendiri menjadi bocoran jawaban. Hanya diagnosis awal yang ditampilkan dengan nama.
- **Terminal dan teks command memakai Geist Mono**. Ini pengecualian dari aturan "hanya Inter", karena output CLI (`bridge vlan show`) butuh kolom yang lurus.
- Garis link topologi memakai hex `#2F6B52` dari design rules, karena belum ada variabelnya.

### Temuan di file Figma
- Judul hero di Home memakai font **Triodion**, padahal design rules menulis "Hanya Inter".
- Home memakai warna mentah (tidak diikat ke variabel) dan ikon navigasinya masih kotak placeholder. Halaman baru sudah memakai variabel dan ikon SVG.
- Bug Plugin API yang ditemui: paint terikat variabel yang dibuat dengan warna dasar hitam tampil hitam di override instance (harus diisi nilai variabel yang sebenarnya), dan `opacity` di paint terikat hilang kalau dipasang sebelum paint ditempel ke node.

---

## 2026-11-03 (5): Golden expert + nyontek, bug pattern checkpoint

### Ditambahkan
- **Golden `20261103-010646` (expert)** dan **`20261103-012346` (nyontek)**, direkam dengan `autoplay.py` di lab sungguhan, masing-masing dengan `notes.md` dan `expected.yaml`. Rentang LLM di `expected.yaml` ditafsirkan Claude dan perlu dikonfirmasi user.
  - Expert: 11 command, 4/4 checkpoint secara berurutan (diagnose 01:21:06 → locate_fault 01:21:49 → apply_fix 01:22:46 → verify_fix 01:23:05), verify correctness 100.
  - Nyontek: 2 command, direkam setelah `--rearm` (re-inject tanpa sudo).
- **`checkpoints.replay_hits(lab)`**: evaluator sekarang menghitung ulang hit `command_match` dari events dengan `problem.yaml` yang berlaku. Hit `state_check` tetap diambil dari `checkpoints.jsonl`, karena state masa lalu tidak bisa diperiksa ulang. Perbaikan pattern langsung berlaku ke semua sesi lama dan golden tanpa merekam ulang. Perbedaan dengan rekaman dicatat di `rule_based.checkpoints_rescored`.

### Diperbaiki
- **Pattern `diagnose` dan `locate_fault` mencocokkan perintah fix.** `^bridge (-d )?(-j )?vlan( show)?`: bagian `( show)?` yang opsional membuat `bridge vlan add dev eth2 vid 20` ikut cocok. Akibatnya sesi nyontek "mendiagnosis" dengan perintah fix-nya sendiri, dan process gate bernilai 1.0. Pattern baru `^bridge (-d )?(-j )?vlan( show( .*)?)?\s*$` hanya menerima perintah baca. Diuji pada 9 variasi, dan pada playtest user hanya baris `bridge vlan add ...` dan typo `bridge vland show` yang berubah status. Ditemukan berkat golden nyontek.

### Verifikasi
- `--rules-only`: trial-and-error 13/13, expert 12/12, nyontek 12/12. Nyontek kini `diagnose`/`locate_fault` tidak tercapai, dengan gate 0.0.
- **Penilaian LLM ketiga golden (Sonnet 4.6 via 9Router, `--repeat 5`):**

| Golden | Methodology (5 run) | Band | reasoning | Gate | Skor akhir | Check |
|---|---|---|---|---|---|---|
| Expert | 95 ×5 | sistematis | ya | 1.0 | **98.0** | 16/16 |
| Trial-and-error (playtest user) | 42 ×5 | campuran | ya | 1.0 | **36.8** | 17/17 |
| Nyontek | 5 ×5 | tanpa_metode | tidak | 0.0 | **12.0** | 16/16 |

  Urutan expert > trial-and-error > nyontek tercapai dengan sesi sungguhan, dan spread setiap golden 0. Token per run: expert ±9k, nyontek ±8k, trial-and-error ±39k (sesi 151 command).

### Diperbaiki (lanjutan)
- **Bukti berupa rentang event dibuang.** Sonnet menulis `"E2-E3"` di satu run golden expert, sehingga muncul 3 warning dan check "tanpa peringatan" gagal. `evaluate.clean_evidence` sekarang memecah rentang `En-Em` / `En–Em` menjadi bukti per event, dengan syarat semua event-nya ada dan rentangnya maksimal 20 event. ID juga di-trim spasinya.
- **Run median dipilih sembarang saat skor sama.** Kunci sort-nya sekarang `(skor, jumlah warning)`, sehingga di antara skor yang sama, run paling bersih yang terpilih.
- Test: `platform/tests/test_evaluate.py` (5 test). Unit test total: 34 lolos, 2 dilewati. Golden expert diulang: 16/16, tanpa warning.

---

## 2026-11-03 (4): Pengaman reset.sh

### Diperbaiki
- **`labs/net-001/reset.sh` menolak dijalankan sebagai root** (`EUID == 0` → exit 1 dengan pesan). Gejalanya: `sudo ./reset.sh` membuat seluruh `.state/` milik root, sehingga `autoplay.py` gagal dengan `PermissionError: .state/watch.log`, dan lab-shell/watcher juga tidak bisa menulis. Ini kejadian kedua (yang pertama di Fase 0, `inject.sh` gagal menulis `ground_truth.json`). Script ini sudah memanggil `sudo` sendiri untuk containerlab.

---

## 2026-11-03 (3): Process gate, supaya nyontek tidak mengalahkan pemain jujur

### Kenapa
Perkiraan skor dengan bobot net-001 lama: expert ±95, **nyontek ±64**, trial-and-error (playtest user) ±37. Sesi nyontek (langsung fix tanpa diagnosis) mendapat correctness dan efficiency sempurna, sehingga mengalahkan pemain jujur yang berantakan. User menolak urutan ini.

### Diubah
- **`scoring.process_gate()` + `scoring.credited()`**: faktor 0–1 = checkpoint proses (`requires`) yang tercapai **sebelum** checkpoint fix (`before`), dibagi jumlah yang diwajibkan. Dimensi di `applies_to` (default correctness, efficiency) dikalikan faktor ini sebelum masuk skor akhir. Diagnosis *setelah* fix tidak dihitung.
- **`labs/net-001/problem.yaml`**: `scoring.process_gate: {requires: [diagnose, locate_fault], before: apply_fix, applies_to: [correctness, efficiency]}`.
- **`evaluate.py`**: `rule_based.process_gate`, `result.credited` (skor yang dikreditkan; `result.scores` tetap mentah), skor akhir dari `credited`. Checkpoint rule-based sekarang menyimpan `ts`. Gate ikut dikirim ke prompt LLM sebagai konteks ("jangan dinilai ulang"). `expected.yaml` mendukung key `process_gate: <faktor>`.
- **`report.py`**: kolom skor menampilkan `100 → 0` kalau dikreditkan sebagian, plus satu baris penjelasan gate.
- **`rencana.md` bagian 4**: rumus skor akhir dan penjelasan process gate.
- Golden `20261019-234339/expected.yaml`: `process_gate: 1.0`. Skenario `autoplay/nyontek.yaml`: label gate 0.

### Verifikasi
- Simulasi (bobot net-001): expert **96.8** > trial-and-error **36.8** > nyontek **13.2**. Diagnosis setelah fix: 18.0 (gate 0).
- `platform/tests/test_scoring.py` (baru, 7 test): proses lengkap, tanpa proses, diagnosis setelah fix, parsial 0.5, belum ada fix, gate nonaktif, dan urutan expert > trial > cheat.
- Golden lama `--rules-only`: 13/13 lolos. Unit test: 29 lolos, 2 dilewati.

---

## 2026-11-03 (2): Model default 9Router + golden otomatis

### Ditambahkan
- **Model default per preset** (`DEFAULT_MODELS` di `platform/llm/openai_compat.py`). `9router` → `ag/claude-sonnet-4-6`, pemenang uji konsistensi. `--model` / `LAB_LLM_MODEL` tetap menang. `evaluate.py providers` menampilkan `[default: ...]` dan tidak lagi menganggap `LAB_LLM_MODEL` wajib untuk preset itu. Test: `test_preset_default_model`.
- **`platform/autoplay.py`**: memainkan skenario YAML lewat `lab-shell` sungguhan di pseudo-terminal (satu PTY per node, seperti tab ttyd), mengetik per karakter, menunggu prompt kembali, dan menjalankan `checkpoints.py watch` di sampingnya. Opsi `--rearm` (re-inject tanpa sudo, wajib lab sehat), `--capture` (verify.json + salin ke `golden/<sesi>/` + notes.md), dan `--speed`.
  - Jebakan yang dihindari: `.state/events` adalah bind mount, jadi `--rearm` hanya mengosongkan isinya, tidak menghapus direktorinya. Kalau dihapus, container akan menulis ke inode lama.
- **Skenario** `labs/net-001/autoplay/expert.yaml` (11 command, 1 perubahan state, isolasi lewat VLAN 10) dan `nyontek.yaml` (langsung fix + 1 ping).
- **`checkpoints_miss`** di `expected.yaml` (`evaluate.check_golden`) untuk menyatakan checkpoint yang harus *tidak* tercapai, misalnya `diagnose` pada sesi nyontek.
- Dokumentasi: `labs/net-001/README.md` bagian "Golden otomatis (autoplay)".

### Verifikasi
- Smoke test autoplay di container yang berjalan: 3 command di 2 node, exit code terekam (`false` → 1), checkpoint `diagnose`/`locate_fault` dicatat watcher, dan `transcript.attach_outputs` memasang output ke setiap command.
- Unit test: 24 lolos, 2 dilewati.

### Terbuka
- Lab ter-restart (container hidup, tapi link containerlab dan konfigurasi bridge hilang): perlu `./reset.sh` (sudo) sebelum golden bisa direkam.

---

## 2026-11-03: Uji evaluator dengan LLM sungguhan (9Router)

Uji pertama lapisan `platform/llm/` di luar mock server, lewat 9Router lokal (`localhost:20128`, preset `9router`).

### Ditambahkan
- **Preset `9router`** di `PRESETS` (`http://localhost:20128/v1`, ditambahkan user). Key lewat `LAB_LLM_API_KEY`, karena 9Router tetap meminta key walau berjalan lokal.
- **Validasi schema sisi klien**: `schema_errors(value, schema)` di `platform/llm/base.py`. Ini validator JSON Schema mini tanpa dependency (type, enum, properties, required, `additionalProperties: false`, items) yang menghasilkan pesan berpath, misalnya `$.feedback.key_moments[0].note: wajib ada`. `True` sengaja tidak dianggap integer.
- **Perbaikan otomatis 1×** di `Backend.complete_json`: kalau output melanggar schema, request diulang dalam mode instruksi berisi schema, jawaban lama, dan daftar error. Kalau masih salah, hasilnya `LLMError`. `meta` mencatat `schema_retry`, `schema_errors_first`, dan `usage_first`, lalu `structured_output` di-set `False`. Berlaku untuk semua backend.
- **Test** (`platform/tests/test_llm.py`, 17 → 23): `TestSchemaErrors` (3 test), schema diabaikan lalu diperbaiki, schema tetap salah setelah perbaikan, body non-JSON (SSE), dan assert `stream: false`. `MockServer` sekarang bisa membalas body mentah (string).
- Dokumentasi: `platform/llm/README.md` bagian 4 ("Lapis kedua: diterima belum tentu ditegakkan") dan bagian 11 (debugging).

### Diperbaiki
- **9Router membalas SSE, bukan JSON** (`JSONDecodeError` di `_post`). Spesifikasi OpenAI menetapkan default `stream: false`, tapi 9Router default-nya streaming. `openai_compat.py` sekarang selalu mengirim `"stream": false`, dan body non-JSON diubah jadi `LLMError("respons bukan JSON")`, bukan traceback.
- **`KeyError: 'evidence'` di `evaluate.validate()`**. 9Router menerima `response_format` json_schema tanpa error, tapi tidak menegakkannya. Gemini membalas dengan bentuk bebas (`checkpoints` alih-alih `llm_checkpoints`, `evidence` berupa string, `key_moments[].reason` alih-alih `note`), dengan 15–17 pelanggaran per jawaban. Diselesaikan dengan validasi dan perbaikan di atas.

### Verifikasi
- `evaluate.py llm-test --provider 9router --model ag/gemini-3.8-flash` → `ok: true`.
- `evaluate.py check golden/20261019-234339` (Gemini 3.8 Flash, 1 run) → **14/15 lolos**. Correctness 50, efficiency 0, safety 50, methodology 48 (`campuran`), final 39.2. Percobaan pertama melanggar schema, retry valid, tanpa warning.
- Satu-satunya yang gagal: `llm checkpoint reasoning = True, harus False`. LLM berargumen bahwa user memeriksa tabel VLAN di sw1/sw2/sw3 (E3–E18) sebelum perubahan pertama (E23). Ini perbedaan interpretasi kriteria, bukan bug. Lihat "Terbuka".
- Unit test: 23 lolos, 2 dilewati (SDK `anthropic`/`litellm` tidak ada di Python sistem).

### Diubah
- **`labs/net-001/golden/20261019-234339/expected.yaml`: `llm_checkpoints.reasoning` `false` → `true`** (keputusan user). Memeriksa tabel VLAN di sw2/sw1/sw3 (E3–E18) sebelum perubahan pertama (E23) dihitung sebagai hipotesis level VLAN/trunk. Eksekusi yang salah sasaran sudah dihukum lewat methodology (`campuran`) dan safety. Kriteria di `problem.yaml` tidak diubah. Dengan ini, hasil run tunggal Gemini menjadi 15/15.

- **Progres real-time di `evaluate.py`** (kelas `Progress`, ke stderr supaya stdout tetap bersih). Di terminal muncul timer berjalan "menunggu model... 23s". Di file/pipe, satu baris per kejadian (cocok untuk `tail -f`). Setiap run selesai menampilkan methodology, band, checkpoint llm_judge, status schema (ok/retry), token (termasuk percobaan pertama yang di-retry), dan jumlah warning. `meta.elapsed_s` dicatat di `evaluation.json`.

### Hasil konsistensi: Gemini 3.8 Flash (`--repeat 5`, via 9Router)
| Run | Methodology | Band | reasoning | Schema |
|---|---|---|---|---|
| 1 | 44 | campuran | ya | retry |
| 2 | 48 | campuran | ya | retry |
| 3 | 42 | campuran | ya | retry |
| 4 | 48 | campuran | ya | retry |
| 5 | 45 | campuran | ya | retry |

- Median 45, rentang 42–48. **Spread 6 > batas `max_spread: 5`**, satu-satunya kriteria yang gagal setelah `reasoning` diubah ke `true`. Band dan checkpoint konsisten 5/5, tanpa warning.
- **Semua 5 run butuh retry schema.** Gemini via 9Router tidak pernah mengikuti schema di percobaan pertama, sehingga biaya token sekitar 2× (±75k token per run). Durasi ±6 menit untuk 5 run.

### Hasil konsistensi: Claude Sonnet 4.6 (`--repeat 5`, via 9Router)
- Methodology **42, 42, 42, 42, 42** (spread 0), band `campuran`, `reasoning=ya`, tanpa warning. **16/16 lolos** terhadap `expected.yaml` yang baru. Skor akhir 36.8.
- **Schema dipatuhi di percobaan pertama** (`structured_output: true`, tanpa retry), ±39k token per run, ±6 menit untuk 5 run.
- Temuan: 9Router meneruskan `response_format` untuk model Claude tapi tidak untuk Gemini. Kepatuhan schema itu sifat pasangan gateway + model, bukan sifat provider. Itu sebabnya validasi sisi klien diperlukan.

### Perbandingan
| | Gemini 3.8 Flash | Claude Sonnet 4.6 |
|---|---|---|
| Golden check | 15/16 (spread 6 > 5) | **16/16** |
| Methodology (median, rentang) | 45 (42–48) | 42 (42–42) |
| Skor akhir (run median) | 38.0 | 36.8 |
| Schema percobaan pertama | 0/5 | 5/5 |
| Token per run | ±75k (dengan retry) | ±39k |

### Diperbaiki (lanjutan)
- **Pengecekan `max_spread` di `evaluate.check_golden`**: memakai `<`, sehingga spread yang sama dengan batas dianggap gagal, dan pesannya terbaca "6 < 5". Sekarang `<=` dengan pesan "selisih methodology antar-run = 6, maks 5".

### Terbuka
- Model default untuk evaluator saat lewat 9Router: Claude Sonnet 4.6 paling konsisten dan paling hemat token di uji ini.
- `max_spread: 5` dipertahankan. Gemini Flash meleset tipis (6), tapi band-nya tetap konsisten.

---

## 2026-10-17 s.d. 2026-10-27: Fase 0–2 (ringkasan awal)

Ringkasan pekerjaan sebelum changelog ini dibuat. Detail desain ada di `rencana.md` bagian 11.

- **Fase 0:** soal `labs/net-001` (VLAN 20 hilang dari trunk sw2), Containerlab 3 switch Linux bridge + 2 host, `inject.sh`, `verify.sh` (preflight akses docker, correctness 0/50/100), `reset.sh`, `brief.md`, `problem.yaml`.
- **Fase 1:** telemetry. `platform/lab-rc.sh` (hook `PROMPT_COMMAND` → JSONL), `platform/lab-shell` (rekaman `script` + timing), `platform/serve` (ttyd + watcher), `platform/checkpoints.py` (matcher `command_match` / `state_check`).
- **Fase 2:** evaluator offline. `platform/transcript.py` (timeline E1..En, output diselaraskan per waktu, 151/151 cocok), `platform/scoring.py`, `platform/prompts/evaluator-system.md`, `platform/evaluate.py` (`run`, `check`, `providers`, `llm-test`), golden transcript `labs/net-001/golden/20261019-234339` (cek deterministik 12/12).
- **Lapisan LLM provider-agnostic:** `platform/llm/` (Anthropic first-party/Bedrock/Vertex, 12 preset OpenAI-compatible, LiteLLM), registry `@register`, fallback structured → instruksi, panduan `platform/llm/README.md`, 17 test offline.
- **Diperbaiki selama fase ini:** penyelarasan output dari berbasis teks (65/151) ke berbasis waktu dengan delay kumulatif semua entri timing (151/151); preseden `build_prompt`; aturan safety `any_of` yang mengabaikan pattern level-rule; ResourceWarning di test.
