# Instalasi

[Beranda](../README.md) › Instalasi

Singkatnya: `./install.sh`, lalu buka http://localhost:8000. Halaman ini
menjelaskan apa saja yang dilakukan installer, pilihan yang tersedia, dan cara
memasang secara manual kalau installer tidak cocok dengan sistemmu.

**Isi halaman:** [Pilih mode](#pilih-mode-pribadi-atau-server) · [Kebutuhan](#kebutuhan) · [Installer](#menjalankan-installer) ·
[Deploy tanpa sudo](#deploy-lab-tanpa-sudo) · [RouterOS](#lab-mikrotik-routeros) ·
[Evaluator AI](#evaluator-ai) · [Service](#service-web-ui) · [Update](#update) ·
[Uninstall](#uninstall) · [Manual](#instalasi-manual) · [Masalah umum](#masalah-umum)

## Pilih mode: Pribadi atau Server

P-lab punya dua mode. Pilih dulu sebelum menjalankan installer.

| | **Pribadi** | **Server** |
|---|---|---|
| Untuk | satu orang di komputernya sendiri | sekolah, kantor, atau rumah dengan banyak pengguna (10-40 bersamaan) |
| Perintah | `./install.sh` | `./install.sh --server` |
| Service | systemd **user** | systemd **system**, berjalan sebagai user `plab` |
| Alamat | hanya `127.0.0.1:8000` | `0.0.0.0:8000`, dibuka dari browser komputer lain di LAN |
| Login | tidak ada | wajib; akun dibuat admin |
| Lab | satu set lab di folder project | tiap pengguna mendapat lab sendiri |
| Data | folder project | `data_dir` (default `/var/lib/p-lab`) |
| Konfigurasi | `~/.config/p-lab/web.env` | `/etc/p-lab/server.yaml` |

Pakai **Pribadi** kalau kamu belajar sendiri. Pakai **Server** kalau satu mesin
akan dipakai banyak orang lewat browser, misalnya satu kelas atau satu tim.
Sisa halaman ini membahas mode Pribadi. Mode Server dibahas di
[Mode Server](server.md), termasuk cara beralih dari Pribadi.

Mode Server dipasang bertahap (bukan satu klik): `./install.sh --server`, isi
`/etc/p-lab/server.yaml`, `./install.sh --server --check`, lalu
`./install.sh --server --migrate` yang membuat admin pertama dan menyalakan
service. Akun lain dibuat dengan `sudo platform/p-lab-admin ...`. Folder repo
harus bisa dilewati user `plab` (disarankan `/opt/p-lab`). Selama config mode
Server ada di mesin, `./install.sh` biasa tidak memasang service Pribadi.

## Kebutuhan

| Komponen | Versi | Untuk apa |
|---|---|---|
| Linux | Arch/CachyOS/Manjaro, Debian/Ubuntu, Fedora | distro lain bisa, tapi dependensi dipasang manual |
| Docker Engine | 24+ | menjalankan node lab sebagai container |
| [containerlab](https://containerlab.dev/install/) | 0.62+ | membuat topologi (switch, host, link) |
| ttyd | 1.7+ | opsional: hanya untuk `platform/serve` (mode terminal tanpa web UI) |
| Python | 3.10+ dengan `venv` | server web, perekam, evaluator |
| Node.js + npm | 20.19+ | build web UI (sekali, saat install/update) |
| util-linux (`script`) | | rekaman input + output terminal |
| KVM | | hanya untuk lab MikroTik RouterOS ([detail](#lab-mikrotik-routeros)) |

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

> [!WARNING]
> Anggota `clab_admins` praktis setara root lewat containerlab, sama seperti
> anggota grup `docker`. Ini wajar untuk komputer pribadi dengan satu pengguna.
> Jangan aktifkan di mesin yang dipakai bersama orang yang tidak kamu percaya.

Untuk membatalkan: `sudo platform/setup-sudoless.sh --undo`.

## Lab MikroTik RouterOS

Lab `net-002` (Subnetting Dasar) dan `net-003` (OSPF Neighbor Stuck) memakai
router **MikroTik RouterOS v7**. MikroTik tidak merilis image container x86
untuk RouterOS, jadi lab ini memakai **CHR** (Cloud Hosted Router), yaitu
image VM resmi MikroTik. CHR dijalankan dengan QEMU di dalam container lewat
[vrnetlab](https://github.com/srl-labs/vrnetlab), dan containerlab mengenalnya
sebagai kind `mikrotik_ros`.

Image-nya dibangun sekali. Installer menawarkannya di tahap 4, atau jalankan
sendiri:

```bash
platform/build-routeros-image.sh          # → vrnetlab/mikrotik_routeros:7.20.4
```

Script itu mengambil vrnetlab ke `~/.cache/p-lab/vrnetlab`, mengunduh
`chr-<versi>.vmdk` (±50 MB) dari download.mikrotik.com, lalu menjalankan `make
docker-image`. Butuh `git`, `curl`, `unzip`, `make`, dan plugin **docker
buildx**. Di Ubuntu/Debian, pasang dengan `sudo apt install docker-buildx`, atau
`docker-buildx-plugin` kalau Docker dari repo docker.com. Tanpa plugin itu,
build gagal dengan `unknown flag: --platform`.

| Kebutuhan | Keterangan |
|---|---|
| KVM (`/dev/kvm`) | virtualisasi (VT-x/AMD-V) aktif di BIOS. Di dalam VM, harus pakai nested virtualization (lihat bawah). Tanpa KVM, CHR diemulasi penuh: boot bisa lebih dari 5 menit dan deploy kemungkinan melewati `ready_timeout` |
| RAM | ±256 MB per router (net-003: 3 router) |
| Waktu deploy | 2–4 menit: router harus boot, lalu OSPF konvergen |

CHR tanpa lisensi berbayar berjalan dalam mode *free*, dengan upload dibatasi
1 Mbit/s per interface. Batas ini tidak berpengaruh untuk lab troubleshooting.

### P-lab di dalam VM

CHR sendiri adalah VM. Kalau P-lab dijalankan di dalam VM (VirtualBox,
VMware, virt-manager, Hyper-V), hasilnya VM di dalam VM. Supaya cepat, CPU VM
P-lab harus meneruskan virtualisasi ke dalam (*nested virtualization*), sehingga
`/dev/kvm` muncul di dalamnya. Matikan VM-nya dulu, lalu:

| Hypervisor (di host) | Cara mengaktifkan |
|---|---|
| virt-manager / KVM (host Linux) | CPU model `host-passthrough`. Cek host: `cat /sys/module/kvm_intel/parameters/nested` (atau `kvm_amd`) harus `Y`/`1` |
| VirtualBox | Settings → System → Processor → **Enable Nested VT-x/AMD-V**, atau `VBoxManage modifyvm <vm> --nested-hw-virt on` |
| VMware Workstation/Fusion | Settings → Processors → **Virtualize Intel VT-x/EPT or AMD-V/RVI** |
| Hyper-V (host Windows) | `Set-VMProcessor -VMName <vm> -ExposeVirtualizationExtensions $true` (PowerShell admin) |

Setelah VM dinyalakan, cek dengan `ls -l /dev/kvm` dan `./install.sh --check`.
Kalau `/dev/kvm` ada tapi tidak bisa diakses, jalankan `sudo usermod -aG kvm
$USER` lalu login ulang. Di host Windows, VirtualBox kadang tidak bisa memakai
nested virtualization kalau Hyper-V/WSL2 aktif. Lab Linux (`net-001`) tidak
butuh KVM sama sekali.

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

### Versi

Nomor versi ada di file `VERSION` (misalnya `0.3.0`). Selama masih `0.x`, format
config dan data bisa berubah antar-versi; langkah tambahannya ditulis di catatan
rilis. Setiap rilis diberi tag git (`v0.3.0`), jadi kamu bisa memasang versi
tertentu, bukan `main` yang terus bergerak:

```bash
git fetch --tags
git checkout v0.3.0
./install.sh            # mode Server: ./install.sh --server
```

Untuk mengetahui kode mana yang sedang dipakai, lihat salah satu:

- baris pertama keluaran `./install.sh` (juga `--check`): `P-lab 0.3.0 (f75e43c, main)`;
- log service saat start: `journalctl --user -u p-lab` (Pribadi) atau `sudo journalctl -u p-lab` (Server), cari `P-lab 0.3.0`;
- dasar sidebar web: `P-lab v0.3.0 · f75e43c`.

Tanda `*` atau "ada perubahan lokal" berarti ada file di repo yang diubah dan belum
di-commit. Sertakan baris versi ini saat melaporkan masalah.

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
| Terminal di web menampilkan `login:` dan tidak bisa diketik (Ubuntu/Debian) | Itu ttyd milik service systemd `ttyd` bawaan paket distro, bukan terminal lab. Sejak versi ini server hanya memakai ttyd yang menjalankan lab-shell, dan memilih port lain kalau 7681 dipakai proses lain. Update (`git pull && ./install.sh`), lalu matikan service bawaannya: `sudo systemctl disable --now ttyd`. |
| `Permission denied` di `.venv` / `EACCES` di `web/node_modules`, lalu `Cannot find native binding` (rolldown) | Folder itu milik root karena installer atau npm pernah dijalankan dengan `sudo`. Jalankan `./install.sh` **tanpa sudo**. Installer mendeteksinya dan menawarkan `sudo chown -R $USER: .venv web/node_modules web/dist ~/.npm`. Error rolldown hanya akibat `npm ci` yang gagal di tengah jalan, jadi akan hilang setelah install ulang berhasil. |
| Terminal di web kosong atau "Terputus" | Server tidak jalan, atau node lab belum berjalan. Terminal web sekarang lewat server (port 8000), tidak butuh ttyd. Cek `systemctl --user status p-lab` (mode Server: `systemctl status p-lab`) dan deploy ulang lab. |
| `web/dist belum ada` | Build web UI gagal. Jalankan `cd web && npm ci && npm run build` dan perhatikan error-nya. Penyebab tersering: versi Node terlalu lama. |
| Port 8000 sudah dipakai | Jalankan server di port lain: `platform/web --port 8080` (atau ubah `ExecStart` di `~/.config/systemd/user/p-lab.service`). |
| Web: "Image vrnetlab/mikrotik_routeros:... belum ada" | Lab RouterOS butuh image yang dibangun lokal: `platform/build-routeros-image.sh` ([detail](#lab-mikrotik-routeros)). |
| Deploy lab RouterOS gagal di tahap `verify` setelah beberapa menit | Router belum selesai boot dalam `deploy.ready_timeout`. Cek `docker logs clab-net002-r1`. Tanpa KVM, boot bisa lebih dari 5 menit. |
| venv rusak setelah folder project dipindah | Jalankan `./install.sh` lagi. Installer mendeteksinya dan membuat ulang `.venv`. |
