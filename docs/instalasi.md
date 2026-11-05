# Instalasi

Singkatnya: `./install.sh`, lalu buka http://localhost:8000. Halaman ini
menjelaskan apa saja yang dilakukan installer, pilihan yang tersedia, dan cara
memasang secara manual kalau installer tidak cocok dengan sistemmu.

## Kebutuhan

| Komponen | Versi | Untuk apa |
|---|---|---|
| Linux | Arch/CachyOS/Manjaro, Debian/Ubuntu, Fedora | distro lain bisa, tapi dependensi dipasang manual |
| Docker Engine | 24+ | menjalankan node lab sebagai container |
| [containerlab](https://containerlab.dev/install/) | 0.62+ | membuat topologi (switch, host, link) |
| ttyd | 1.7+ | terminal node di browser |
| Python | 3.10+ dengan `venv` | server web, perekam, evaluator |
| Node.js + npm | 20.19+ | build web UI (sekali, saat install/update) |
| util-linux (`script`) | | rekaman input + output terminal |

Ukuran: image `nicolaka/netshoot` sekitar 200 MB. Lab net-001 (5 node) memakai kurang dari 1 GB RAM.

Evaluator AI butuh akses ke satu provider LLM, bisa cloud atau lokal. Tanpa
provider, penilaian tetap jalan; hanya methodology dan skor akhir yang kosong.

## Menjalankan installer

```bash
./install.sh
```

Ada enam tahap. Installer **bertanya dulu** sebelum melakukan apa pun yang butuh sudo.

1. **Dependensi sistem**: cek semua komponen di tabel di atas. Yang belum ada
   dipasang lewat package manager distro (`pacman`, `apt`, atau `dnf`).
   containerlab dipasang lewat AUR (`paru`/`yay`) di Arch, atau lewat installer
   resminya di distro lain. Installer juga menawarkan untuk menambahkan kamu ke
   grup `docker`, supaya docker bisa dipakai tanpa sudo.
2. **Python**: membuat `.venv/` di folder project dan memasang `platform/requirements.txt`.
3. **Web UI**: `npm ci` dan `npm run build` di `web/`.
4. **Image container**: mengunduh semua image yang dipakai lab di `labs/`, lalu
   memeriksa semua lab dengan `lab-lint`.
5. **Service**: memasang service systemd user `p-lab`, yang menjalankan web UI
   setiap kali kamu login, dan ikon **P-lab** di menu aplikasi.
6. **Deploy dari web** (opsional): lihat [bagian berikut](#deploy-lab-tanpa-sudo).

Kalau installer menambahkanmu ke grup baru (`docker`, `clab_admins`), **logout
lalu login lagi** supaya grupnya aktif.

### Opsi

| Opsi | Arti |
|---|---|
| `--check` | hanya mengecek dan melaporkan, tidak mengubah apa pun |
| `--yes` | jawab "ya" untuk semua pertanyaan (non-interaktif) |
| `--no-deps` | jangan memasang package sistem; berguna kalau kamu memasangnya sendiri |
| `--no-service` | jangan memasang service; jalankan web UI manual dengan `platform/web` |
| `--sudoless` / `--no-sudoless` | aktifkan atau lewati deploy dari web tanpa bertanya |

## Deploy lab tanpa sudo

containerlab butuh hak root untuk membuat network namespace dan link virtual.
Ada dua cara memberikannya:

- **Tanpa setup**: kamu men-deploy dari terminal dengan `./reset.sh` di folder
  lab, dan password sudo diminta setiap kali.
- **Dengan setup sekali** (`sudo platform/setup-sudoless.sh`): tombol **Deploy &
  mulai** dan **Reset lab** di web langsung jalan, dan `./reset.sh` tidak lagi
  meminta password.

Setup ini memakai mekanisme bawaan containerlab: binary-nya dijadikan setuid root
dan hanya bisa dijalankan anggota grup `clab_admins`. Di Arch, script juga
memasang pacman hook supaya pengaturan ini tidak hilang saat containerlab di-update.

> **Konsekuensi keamanan:** anggota `clab_admins` praktis setara root lewat
> containerlab, sama seperti anggota grup `docker`. Ini wajar untuk komputer
> pribadi dengan satu pengguna. Jangan aktifkan di mesin yang dipakai bersama
> orang yang tidak kamu percaya.

Untuk membatalkan: `sudo platform/setup-sudoless.sh --undo`.

## Evaluator AI

"Nilai dengan AI" membaca konfigurasi dari `~/.config/p-lab/web.env`, yang
dibuat installer. Contoh untuk Anthropic:

```bash
# ~/.config/p-lab/web.env
LAB_LLM_PROVIDER=anthropic
LAB_LLM_MODEL=claude-sonnet-4-6
LAB_LLM_API_KEY_FILE=/home/<user>/.config/lab/anthropic.key
```

Simpan API key di file terpisah (`chmod 600`) dan tunjuk lokasinya lewat
`LAB_LLM_API_KEY_FILE`, supaya key tidak tertulis di file konfigurasi. Daftar
provider dan variabelnya ada di [platform/llm/README.md](../platform/llm/README.md).
Setelah mengubah file ini, jalankan `systemctl --user restart p-lab`.

Untuk menguji koneksi: `.venv/bin/python platform/evaluate.py llm-test`.

## Service web UI

```bash
systemctl --user status p-lab      # status
systemctl --user restart p-lab     # setelah mengubah web.env atau kode server
journalctl --user -u p-lab -f      # log
platform/install-service.sh --uninstall
```

Tanpa systemd, misalnya di container atau WSL, jalankan `platform/web` di
terminal dan biarkan terbuka.

## Update

```bash
git pull
./install.sh
```

Installer aman dijalankan berulang. Ia memasang paket Python dan npm yang
berubah, membangun ulang web UI, lalu me-restart service.

## Uninstall

```bash
platform/install-service.sh --uninstall       # service + ikon
sudo platform/setup-sudoless.sh --undo        # kalau pernah diaktifkan
for d in labs/*/; do (cd "$d" && sudo containerlab destroy -t *.clab.yaml --cleanup); done
rm -rf ~/.config/p-lab                        # konfigurasi LLM
```

Setelah itu folder project bisa dihapus. Package sistem (docker, containerlab,
ttyd) tidak ikut dihapus.

## Instalasi manual

Kalau distromu tidak dikenali installer:

1. Pasang komponen di tabel [Kebutuhan](#kebutuhan). Untuk containerlab:
   `bash -c "$(curl -sL https://get.containerlab.dev)"`.
2. `sudo usermod -aG docker $USER`, lalu login ulang.
3. `./install.sh --no-deps`

## Masalah umum

| Gejala | Penyebab dan solusi |
|---|---|
| `permission denied ... docker.sock` | User belum di grup docker, atau grupnya belum aktif. Jalankan `sudo usermod -aG docker $USER`, lalu logout dan login. |
| Web: "Docker tidak bisa diakses dari server" | Sama seperti di atas. Service mewarisi grup dari sesi login, jadi setelah login ulang jalankan `systemctl --user restart p-lab`. |
| Web masih menampilkan `./reset.sh` setelah setup sudo-less | Grup `clab_admins` belum aktif di proses server. Logout dan login (atau reboot), lalu restart service. |
| Deploy gagal di tahap `verify` | Lab tidak sehat sebelum fault dipasang. Jalankan `./verify.sh` di folder lab untuk melihat masalahnya. Biasanya image belum terunduh atau RAM kurang. |
| "Lab belum sehat ... Jalankan ./reset.sh" saat Mulai sesi | Lab rusak, misalnya container restart setelah reboot sehingga bridge hilang. Pakai **Reset lab** atau `./reset.sh`. |
| Terminal di web kosong | `ttyd` belum terpasang, atau port 7681 dipakai proses lain. Cek dengan `./install.sh --check`. |
| `web/dist belum ada` | Build web UI gagal. Jalankan `cd web && npm ci && npm run build` dan perhatikan error-nya. Penyebab tersering: versi Node terlalu lama. |
| Port 8000 sudah dipakai | Jalankan server di port lain: `platform/web --port 8080` (atau ubah `ExecStart` di `~/.config/systemd/user/p-lab.service`). |
| venv rusak setelah folder project dipindah | Jalankan `./install.sh` lagi. Installer mendeteksinya dan membuat ulang `.venv`. |
