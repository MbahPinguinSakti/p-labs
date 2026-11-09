# Mode Server

[Beranda](../README.md) › Mode Server

Mode Server menjalankan P-lab di satu mesin yang dipakai banyak orang lewat
browser: satu kelas, satu tim IT, atau beberapa orang di rumah. Setiap
pengguna login dengan akunnya sendiri dan mendapat lab sendiri, jadi
kesalahan konfigurasi satu orang tidak mengganggu yang lain.

Kalau kamu hanya memakai P-lab sendirian, tetap di mode Pribadi
([instalasi](instalasi.md#pilih-mode-pribadi-atau-server)).

**Isi halaman:** [Kebutuhan dan sizing](#kebutuhan-dan-sizing) ·
[Instalasi](#instalasi) · [Konfigurasi](#konfigurasi) · [Kapasitas](#batas-kapasitas) · [Antrian](#antrian-deploy) · [Key LLM](#key-llm-untuk-nilai-dengan-ai) · [Akun](#akun) ·
[Dashboard admin](#dashboard-admin) · [Mandiri vs kelas](#gaya-mandiri-atau-kelas) ·
[Halaman kelas](#halaman-kelas) · [Akses dari komputer lain](#akses-dari-komputer-lain) · [Winbox](#winbox-dari-komputer-siswa) ·
[HTTPS](#https-opsional) · [Keamanan](#keamanan) · [Backup](#backup-dan-restore) ·
[Migrasi dari Pribadi](#migrasi-dari-mode-pribadi) · [Masalah umum](#masalah-umum) ·
[Belum tersedia](#belum-tersedia)

## Yang berbeda dari mode Pribadi

- Service berjalan sebagai service systemd **system** dengan user `plab`, aktif sejak mesin menyala (tanpa perlu login ke desktop).
- Login wajib. Tidak ada pendaftaran bebas: admin yang membuat akun.
- Tiga role: `admin` (mengelola akun dan lab yang berjalan), `guru` (melihat progres siswa di gaya `kelas`), dan `siswa`.
- Setiap pengguna mendapat **instance lab terpisah** di `<data_dir>/instances/<user>/<lab>/`.
- Ada [batas kapasitas](#batas-kapasitas). Lab yang tidak disentuh dimatikan otomatis.
- Konfigurasi ada di `/etc/p-lab/server.yaml`, data di `data_dir`.

## Kebutuhan dan sizing

Kebutuhan software sama dengan [mode Pribadi](instalasi.md#kebutuhan). Tambahannya
soal RAM, dan KVM kalau kamu memakai lab RouterOS.

Router RouterOS (CHR) memakai sekitar **256 MB RAM per router** ditambah overhead
container dan QEMU. Lab Linux seperti `net-001` jauh lebih ringan. Yang menentukan
ukuran mesin adalah jumlah lab yang **berjalan bersamaan**, bukan jumlah akun.

| Lab yang dimainkan | RAM per pengguna (perkiraan) | 20 pengguna | 40 pengguna |
|---|---|---|---|
| `net-001` (Linux, 5 node) | 150 MB | 3 GB | 6 GB |
| `net-002` (2 router) | 900 MB | 18 GB | 36 GB |
| `net-003` (3 router) | 1,3 GB | 26 GB | 52 GB |

Angka di atas memakai nilai yang sama dengan perhitungan kapasitas P-lab: per lab
di `problem.yaml` (`resources.mem_mb`), jadi lab yang kamu tambah sendiri sebaiknya
mengisinya juga. Ini perkiraan yang belum diukur di kelas sungguhan; bandingkan
dengan `docker stats` setelah router selesai boot.
Sisakan RAM untuk OS dan server web (minimal 2-4 GB), lalu isi `capacity.mem_mb`
dengan sisanya. Mulai dari angka konservatif, lalu naikkan kalau memang lega.

Lab RouterOS butuh `/dev/kvm`. Di mesin virtual, aktifkan nested virtualization
([detail](instalasi.md#lab-mikrotik-routeros)). Tanpa KVM, boot router bisa lebih
dari 5 menit, jadi tidak realistis untuk kelas.

## Instalasi

Jalankan dari folder project, **sebagai user biasa** (installer meminta sudo
saat perlu). Urutannya selalu sama, untuk instalasi baru maupun peralihan dari
mode Pribadi:

```bash
./install.sh --server                   # 1. pasang: user plab, data_dir, unit systemd. BERHENTI di sini
sudo nano /etc/p-lab/server.yaml        # 2. isi config (dibuat dari template), lihat bagian Konfigurasi
./install.sh --server --check           # 3. pre-flight, tidak mengubah apa pun
./install.sh --server --migrate         # 4. buat admin pertama + nyalakan service (ketik ulang `server`)
```

Penjelasan tiap langkah:

1. `--server` membuat user sistem `plab` (masuk grup `docker`, `kvm`, `clab_admins`), `data_dir` milik `plab`, `/etc/p-lab/server.yaml` dari template, dan unit systemd. Service **belum dinyalakan dan belum di-enable**: setelah reboot pun ia tidak hidup sendiri sebelum kamu menyelesaikan langkah 4.
2. Isi config: minimal `data_dir`, `style`, `capacity.mem_mb`, dan `allowed_hosts`.
3. `--check` memeriksa user dan grup `plab`, repo bisa dibaca `plab`, config valid, RAM dibanding `capacity.mem_mb`, KVM (untuk lab RouterOS), containerlab sudo-less, port di `listen` masih bebas, tidak ada lab yang berjalan, dan admin di database. Sebagai user biasa, `--check` tidak bisa membaca database akun (milik `plab`, mode 0600) dan melaporkannya sebagai peringatan, bukan kegagalan.
4. `--migrate` menjalankan pre-flight lagi, meminta konfirmasi, **membuat admin pertama** (password acak dicetak sekali, catat), menghentikan service pribadi bila ada, lalu menjalankan `systemctl enable --now p-lab`. Untuk instalasi baru ini langkah yang menyalakan service. Kalau kamu beralih dari mode Pribadi, langkah ini juga menyalin riwayat sesi lama ([detail](#migrasi-dari-mode-pribadi)).

Perbaiki semua yang gagal di `--check` sebelum lanjut. Setelah `--migrate`, baru
cek service-nya:

```bash
systemctl status p-lab                  # tanpa --user
journalctl -u p-lab -f                  # log
```

### Syarat folder repo

Service berjalan sebagai user `plab`, jadi `plab` harus bisa membaca repo dan
`.venv`, dan **melewati semua folder induknya** (bit `o+x`). Repo di
`/home/<user>` yang bermode 700 **tidak akan jalan** (service gagal start dengan
`Permission denied`). Dua pilihan:

- **Disarankan:** taruh repo di `/opt/p-lab` (`sudo git clone ... /opt/p-lab && sudo chown -R $USER: /opt/p-lab`), lalu jalankan installer dari sana.
- Atau `chmod o+x /home/<user>` (membuat folder home bisa dilewati, bukan dibaca, oleh user lain).

`plab` hanya membaca repo; ia tidak pernah menulis ke sana. Semua data ada di
`data_dir`, dan web UI di-build oleh installer (bukan oleh service). Setelah
`git pull`, jalankan `./install.sh --server` lagi untuk build ulang dan restart
service.

## Konfigurasi

`/etc/p-lab/server.yaml` (bisa diganti dengan env `LAB_CONFIG`):

```yaml
mode: server              # pribadi | server
listen: 0.0.0.0:8000
data_dir: /var/lib/p-lab  # DB akun (p-lab.db), instances/<user>/<lab>/, arsip
style: mandiri            # mandiri | kelas
capacity:
  mem_mb: 24000           # total estimasi RAM lab yang boleh berjalan
  max_deploys: 2          # deploy bersamaan
  idle_minutes: 30        # lab tanpa aktivitas → diarsip lalu dihancurkan
allowed_hosts:            # disarankan: nama/IP yang dipakai membuka P-lab
  - lab.sekolah.local
  - 192.168.1.10
trusted_proxies: []       # IP/CIDR reverse proxy (kosong kalau tanpa proxy)
winbox_ports: 28000       # opsional: 0 atau dihapus = Winbox dari komputer lain nonaktif
```

| Baris | Arti |
|---|---|
| `mode` | `server` untuk mode ini. `pribadi` mengembalikan perilaku lama. |
| `listen` | alamat dan port. `0.0.0.0:8000` bisa diakses dari jaringan; `127.0.0.1:8000` hanya dari mesin itu (cocok kalau di depannya ada reverse proxy). |
| `data_dir` | semua data mode Server: database akun `p-lab.db`, folder `instances/<user>/<lab>/` (lab dan sesi tiap pengguna), dan arsip sesi. Harus bisa ditulis user `plab`. |
| `style` | `mandiri` atau `kelas`, lihat [bagian berikut](#gaya-mandiri-atau-kelas). |
| `capacity.mem_mb` | total estimasi RAM untuk semua lab yang boleh berjalan bersamaan. Deploy yang membuat totalnya melewati batas ini masuk [antrian](#antrian-deploy). Kalau satu lab saja sudah melewati batas, deploy ditolak dengan pesan. |
| `capacity.max_deploys` | berapa deploy yang boleh berjalan bersamaan. Deploy lab RouterOS menguras CPU dan disk, jadi 2 biasanya cukup. Deploy lain masuk [antrian](#antrian-deploy). |
| `capacity.idle_minutes` | lab tanpa aktivitas selama ini (tidak ada command dan halaman lab tidak terbuka) dimatikan untuk membebaskan RAM. Sesi yang belum dinilai **tidak bisa dilanjutkan**: rekamannya disimpan di folder instance, tapi tidak muncul di riwayat. Pengguna perlu deploy lagi dan mulai sesi baru. |
| `allowed_hosts` | opsional tapi **disarankan**: daftar nama host atau IP (yang kamu ketik di browser) yang boleh dipakai membuka P-lab. Permintaan dengan header `Host` lain ditolak; ini mencegah serangan DNS rebinding. Tulis tanpa `http://` dan tanpa port (mis. `[192.168.1.10, lab.sekolah.local]`). Isi semua nama yang dipakai, termasuk IP kalau ada yang membukanya lewat IP. `localhost`, `127.0.0.1`, dan `[::1]` selalu diizinkan supaya admin bisa membuka dari mesin server sendiri. Kosong = semua `Host` diterima (server mencatat peringatan di log). Di mode Pribadi kunci ini tidak boleh diisi. |
| `trusted_proxies` | opsional: IP atau CIDR reverse proxy yang dipercaya. Pembatas percobaan login memakai alamat klien dari `X-Forwarded-For` **hanya** kalau permintaan datang dari alamat di daftar ini; selain itu dipakai alamat koneksi langsung. Daftar yang sama juga menentukan kapan `X-Forwarded-Proto: https` dipercaya untuk memberi flag `Secure` pada cookie login. Isi kalau kamu memasang [proxy HTTPS](#https-opsional), mis. `["127.0.0.1"]`. Proxy wajib meneruskan header `Host` asli; `X-Forwarded-Host` tidak dibaca. |
| `winbox_ports` | opsional: port awal untuk Winbox per router dari komputer lain. `0` atau tidak diisi = nonaktif. Kalau diisi, nilainya 1024 sampai 63488, dan P-lab memakai rentang 2048 port mulai dari nilai ini. Lihat [Winbox dari komputer siswa](#winbox-dari-komputer-siswa). |

Setelah mengubah file ini: `sudo systemctl restart p-lab`.

## Batas kapasitas

Tanpa batas, 30 siswa yang menekan Deploy bersamaan akan membuat mesin hang.
Karena itu P-lab membatasi lewat beberapa aturan, sebagian dari `capacity` di config:

- **RAM (`mem_mb`)**: sebelum deploy, P-lab menjumlahkan perkiraan RAM lab yang sedang berjalan (dari `resources.mem_mb` di `problem.yaml` tiap lab). Kalau lab baru membuat totalnya melewati `mem_mb`, deploy **masuk [antrian](#antrian-deploy)** sampai RAM cukup. Kalau perkiraan satu lab saja sudah melewati `mem_mb`, deploy **ditolak dengan pesan**, karena tidak akan pernah muat.
- **Deploy bersamaan (`max_deploys`)**: hanya sejumlah ini yang boleh berjalan sekaligus. Deploy lain **masuk antrian** dan menunggu giliran.
- **Satu lab per pengguna**: men-deploy lab baru mematikan lab lain milik pengguna yang sama. Siswa tidak bisa memegang beberapa lab sekaligus.
- **Tanpa aktivitas (`idle_minutes`)**: lab yang tidak disentuh selama itu dimatikan untuk membebaskan RAM. Halaman lab yang masih terbuka di browser dihitung sebagai aktivitas. Sesi yang belum dinilai tidak bisa dilanjutkan dan tidak muncul di riwayat, jadi ingatkan pengguna menekan **Selesai & nilai** sebelum pergi.
- **Akun dinonaktifkan**: lab milik akun itu ikut dimatikan, dan antriannya dibuang.

## Antrian deploy

Kalau server sedang penuh, deploy tidak langsung ditolak. Di mode Server ia masuk **antrian**, lalu dijalankan otomatis saat gilirannya tiba dan RAM tersedia.

- **Alasan antre** tampil di halaman lab: *menunggu giliran deploy* (sudah ada `max_deploys` deploy yang berjalan) atau *menunggu RAM server cukup* (lab lain sedang berjalan).
- **Berurutan ketat (FIFO).** Lab kecil tidak menyalip lab di depannya, walaupun RAM untuk lab kecil itu sebenarnya cukup. Akibatnya, pengguna di belakang bisa menunggu lebih lama dari yang diperlukan labnya.
- **Posisi dan batal.** Halaman lab menampilkan posisimu (mis. "posisi 2") dan tombol **Batalkan antrian**. Satu akun hanya boleh punya satu deploy dalam antrian atau yang sedang berjalan. Men-deploy lab lain saat itu ditolak dengan pesan.
- **Batas 30 menit.** Antrian yang menunggu lebih dari 30 menit dibatalkan otomatis, dengan pesan "Antrian deploy dibatalkan: menunggu lebih dari 30 menit."
- **Akun dinonaktifkan.** Antriannya dibuang.
- **Gangguan sementara tidak membuang antrian.** Kalau docker sesaat tidak menjawab, atau pemilik entri terdepan sedang dinilai / labnya sedang dimatikan, antrian menunggu lalu dicoba lagi (paling lambat tiap 10 detik, dan segera setelah ada deploy yang selesai).
- **Antrian ada di memori.** Kalau service P-lab di-restart, antrian kosong lagi dan halaman lab kembali menampilkan tombol Deploy; pengguna cukup menekannya lagi.
- **Lab terlalu besar tidak masuk antrian.** Kalau perkiraan RAM satu lab sendiri sudah melebihi `capacity.mem_mb`, deploy ditolak seperti biasa, karena antrian tidak akan pernah bisa melayaninya. Minta admin menaikkan batas, atau pilih lab yang lebih kecil.

Admin melihat semua antrian di [Lab berjalan](#lab-berjalan).

## Key LLM untuk "Nilai dengan AI"

Fitur penilaian AI memakai provider LLM (lihat [platform/llm/README.md](../platform/llm/README.md)).
Di mode Pribadi, env-nya ada di `~/.config/p-lab/web.env`. Di mode Server
service tidak membaca file itu; ia membaca **`/etc/p-lab/web.env`** (opsional,
formatnya `NAMA=nilai` per baris, tanpa `export`):

```bash
sudo install -m 600 -o root -g root /dev/null /etc/p-lab/web.env
sudo nano /etc/p-lab/web.env
```

```
LAB_LLM_PROVIDER=anthropic
LAB_LLM_API_KEY=sk-...
```

File ini dibaca systemd (sebagai root) sebelum service berpindah ke user `plab`,
jadi cukup mode 600 milik root. Isi key langsung di sini. Kalau memakai
`LAB_LLM_API_KEY_FILE=<path>`, file key itu harus bisa dibaca `plab`. Setelah
mengubahnya: `sudo systemctl restart p-lab`. Tanpa file ini, P-lab tetap jalan;
hanya tombol penilaian AI yang tidak berfungsi.

## Akun

Akun bisa dikelola dari [dashboard admin](#dashboard-admin) di web. CLI
`platform/p-lab-admin` tetap ada, dijalankan di mesin server, dan dipakai untuk
admin pertama serta saat web tidak bisa diakses. Tidak ada registrasi bebas.
**Selalu pakai `sudo`** untuk CLI: database akun milik user `plab`
(mode 0600), dan `p-lab-admin` berjalan sebagai `plab` supaya database tidak
pernah dibuat milik root (yang membuat service gagal start). Tanpa `sudo`, user
biasa ditolak dengan pesan yang menunjukkan perintah yang benar.

```bash
sudo platform/p-lab-admin create-user budi --name "Budi Santoso"              # role siswa (default)
sudo platform/p-lab-admin create-user bu-ani --role guru --name "Ani Wijaya"
sudo platform/p-lab-admin create-user admin2 --role admin
sudo platform/p-lab-admin list                                                # semua akun
sudo platform/p-lab-admin list --role siswa
sudo platform/p-lab-admin reset-password budi
sudo platform/p-lab-admin set-role budi guru
sudo platform/p-lab-admin deactivate budi                                     # cabut akses, data tetap
sudo platform/p-lab-admin activate budi
```

Password ditanyakan lewat prompt (tidak tampil di riwayat shell). Untuk
skrip, kirim lewat stdin dengan `--password-stdin`.

Aturan:

- **Username**: huruf kecil, angka, dan tanda hubung, 1-32 karakter, tidak diawali tanda hubung (`^[a-z0-9][a-z0-9-]{0,31}$`); nama `local` dicadangkan sistem. Username dipakai sebagai nama folder dan nama container lab, jadi tidak boleh ada huruf besar, spasi, atau titik.
- **Password**: minimal 8 karakter.
- **Sesi login**: berlaku 12 jam sejak login, lalu pengguna login lagi. Mengganti password atau menonaktifkan akun langsung mencabut semua sesinya.
- Admin aktif terakhir tidak bisa dinonaktifkan atau diturunkan rolenya, supaya sistem tidak terkunci.

### Import dari CSV

Untuk satu kelas, buat file CSV dengan kolom `username,display_name,role,password`:

```csv
username,display_name,role,password
budi,Budi Santoso,siswa,
sari,Sari Dewi,siswa,
andi,Andi Pratama,siswa,rahasia-123
bu-ani,Ani Wijaya,guru,
```

```bash
sudo platform/p-lab-admin import-csv kelas-10a.csv
```

- Password yang **dikosongkan** diganti password acak. Password acak dicetak sekali di layar saat import, jadi simpan atau bagikan langsung. Tidak bisa dilihat lagi nanti (yang tersimpan hanya hash); kalau hilang, pakai `reset-password`.
- Import berjalan **per baris**. Baris yang salah (username tidak valid, role tidak dikenal, username sudah ada, password terlalu pendek) dilaporkan dengan nomor barisnya dan tidak membatalkan baris lain. Perbaiki baris yang gagal, simpan di file kecil, lalu import ulang.

> [!NOTE]
> `p-lab-admin` membaca `/etc/p-lab/server.yaml` untuk menemukan
> `<data_dir>/p-lab.db`, database yang sama dengan service. `sudo` membuang env,
> jadi kalau memakai lokasi config lain, jalankan
> `sudo env LAB_CONFIG=<path> platform/p-lab-admin ...`.
>
> File CSV harus bisa dibaca user `plab`, dan bisa berisi password. Jangan taruh
> di `/tmp` (terbaca semua user lokal). Salin khusus untuk `plab`, lalu hapus:
> `sudo install -o plab -m 600 daftar.csv /var/lib/p-lab/daftar.csv`, import,
> lalu `sudo rm /var/lib/p-lab/daftar.csv`.

## Dashboard admin

Admin melihat bagian **Admin** di sidebar, berisi menu **Akun** dan **Lab berjalan**.
Kedua halaman hanya bisa dibuka role `admin`.

### Akun

Halaman **Akun** menampilkan semua akun: nama, username, role, status aktif, dan
terakhir terlihat (mis. "5 menit lalu"). Filter nama/username dan filter role ada di
atas tabel.

| Aksi | Yang terjadi |
|---|---|
| **Tambah akun** | Isi username, nama, role, dan password. Kosongkan password untuk dibuatkan password acak. |
| **Import CSV** | Tempel isi CSV dengan kolom `username,display_name,role,password` di kotak teks, lalu pilih role default. CSV dari Excel dengan pemisah titik koma (`;`) juga diterima. Hasilnya berupa daftar akun yang berhasil dibuat beserta password acaknya, dan daftar baris yang gagal beserta pesannya. Seperti CLI, import berjalan per baris. |
| **Ubah** | Membuka dialog untuk mengganti nama tampilan (maksimal 100 karakter) dan role, lalu **Simpan**. |
| **Nonaktifkan** / **Aktifkan** | Minta konfirmasi. Saat dinonaktifkan, sesi login akun itu langsung berakhir dan lab-nya ikut dimatikan. Sesi yang belum dinilai diarsipkan sebagai ditinggalkan dan tidak bisa dilanjutkan. Antrian deploy akun itu dibuang. Kalau lab itu sedang di-deploy, dinilai, atau sedang dimatikan, lab itu dilewati dan dimatikan otomatis dalam satu menit setelah selesai (pesan sukses menyebut jumlahnya). |
| **Reset password** | P-lab membuat password acak baru dan menampilkannya **sekali**. Semua sesi login akun itu ikut dicabut. Tidak tersedia untuk akunmu sendiri, karena sesimu ikut berakhir sebelum password baru terlihat; ganti password sendiri dengan `sudo platform/p-lab-admin reset-password <username>`. |

Password acak (dari tambah akun, import, atau reset password) tampil di modal
dengan tombol **Salin** dan peringatan untuk langsung mencatatnya. Setelah modal
ditutup, password itu tidak bisa dilihat lagi; kalau hilang, lakukan reset password.
Hasil import juga bisa disalin sebagai teks `username,password` per baris.

Aturan yang dijaga server:

- Admin tidak bisa menurunkan role, menonaktifkan, atau mereset password **akunnya sendiri** dari web. Di baris akunnya, tombol Nonaktifkan dan Reset password nonaktif, dan pilihan role di dialog Ubah terkunci.
- Admin aktif terakhir tidak bisa dinonaktifkan atau diturunkan rolenya.
- Tidak ada tombol hapus akun. Nonaktifkan saja (lihat [belum tersedia](#belum-tersedia)).

### Lab berjalan

Halaman **Lab berjalan** menampilkan:

- **Kapasitas**: perkiraan RAM yang terpakai dibanding `capacity.mem_mb`, jumlah deploy yang sedang berjalan dibanding `max_deploys`, jumlah yang mengantre, dan batas `idle_minutes`.
- **Daftar lab**: satu baris per lab per pengguna, dengan status (`berjalan`, `deploy` beserta tahapnya, atau `berhenti`), perkiraan RAM, aktivitas terakhir, dan sesinya.
- **Antrian deploy**: posisi, pengguna (nama dan username), lab, alasan (`slot deploy` atau `RAM`), dan sejak kapan menunggu. Bagian ini hanya muncul kalau ada yang mengantre.

Halaman ini memuat ulang sendiri tiap 10 detik, dan ada tombol segarkan manual.
Kalau tidak ada lab yang berjalan, halaman menampilkan "Tidak ada lab yang berjalan."

Tombol **Matikan** menghentikan lab satu pengguna. Sebelum dikonfirmasi, P-lab
mengingatkan bahwa sesi yang belum dinilai akan diarsipkan sebagai ditinggalkan.
Lab yang sedang di-deploy, sedang dinilai, atau sedang dimatikan tidak bisa dimatikan: tombolnya
nonaktif, dan tooltip menjelaskan alasannya.

## Gaya mandiri atau kelas

Diatur lewat `style` di config.

| | `mandiri` | `kelas` |
|---|---|---|
| Hubungan antar pengguna | semua setara | guru dan siswa |
| Leaderboard | ada; semua pengguna tampil dengan nama | ada, anonim: siswa melihat teman sebagai "Siswa lain", guru dan admin melihat nama |
| Guru | tidak ada peran khusus | melihat progres semua siswa |
| Cocok untuk | tim IT, komunitas, belajar bareng | kelas dengan guru yang menilai |

Di kedua gaya, siswa hanya melihat sesi dan hasilnya sendiri. Di gaya `kelas`,
guru dan admin juga melihat progres semua siswa di [halaman kelas](#halaman-kelas).

## Halaman kelas

Halaman kelas hanya ada di gaya `kelas`. Menunya **Progres kelas** muncul di sidebar
untuk guru dan admin. Di gaya `mandiri` menu ini tidak ada, dan tidak ada halaman
yang menampilkan sesi siswa lain.

- **Tabel progres** (`/kelas`): satu baris per siswa aktif dan satu kolom per lab.
  Setiap sel berisi skor terbaik dan jumlah percobaan, atau `–` kalau belum
  dikerjakan. Ada juga kolom poin, jumlah sesi, dan sesi terakhir. Tabel diurutkan
  menurut poin; klik judul kolom nama untuk mengurutkan menurut nama. Klik baris
  siswa untuk membuka detailnya. Poin dihitung seperti di halaman Progress: skor
  terbaik tiap lab dijumlahkan, jadi mengulang lab tidak menambah poin.
- **Detail siswa** (`/kelas/<username>`): nama dan poin siswa, lalu daftar sesinya
  (lab, tanggal, durasi, jumlah command, skor, dan band). Klik sesi untuk membuka
  laporannya, sama seperti halaman Hasil.
- **Export CSV**: tombol di halaman progres mengunduh `nilai-kelas.csv` dengan kolom
  `username`, `nama`, `poin`, `sesi`, lalu skor terbaik tiap lab (kosong kalau belum
  dikerjakan). Sel yang diawali `=`, `+`, `-`, atau `@` diberi awalan `'` supaya
  tidak dijalankan sebagai rumus saat dibuka di spreadsheet.

Akun siswa yang nonaktif tidak ditampilkan.

## Akses dari komputer lain

Dari browser komputer lain di jaringan yang sama, buka
`http://<ip-server>:8000`. Cari IP server dengan `ip -4 addr`.

Kalau tidak bisa dibuka, periksa firewall di server:

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8000 proto tcp   # Ubuntu (ufw), sesuaikan subnet
sudo firewall-cmd --permanent --add-port=8000/tcp && sudo firewall-cmd --reload   # Fedora
```

Batasi ke subnet LAN, jangan ke seluruh internet. **Jangan membuka P-lab ke
internet.**

**Winbox:** perubahan yang dibuat lewat Winbox tetap direkam dan dinilai seperti
di mode Pribadi (lihat [Memakai Winbox](penggunaan.md#memakai-winbox)). Cara
membukanya dari komputer siswa ada di [Winbox dari komputer siswa](#winbox-dari-komputer-siswa).

## Winbox dari komputer siswa

Di mode Server, siswa bisa membuka Winbox ke router labnya langsung dari
komputernya sendiri, tanpa tunnel SSH. Fitur ini aktif kalau `winbox_ports`
diisi di config. Kalau kosong atau `0`, panel Winbox hanya menampilkan alamat
internal yang terjangkau dari mesin server (lihat [Winbox](penggunaan.md#memakai-winbox)).

```yaml
winbox_ports: 28000
```

Port tiap router dihitung dengan rumus:

```
port = winbox_ports + nomor_user × 8 + urutan_router
```

- `nomor_user`: nomor subnet management pengguna (0 sampai 255, kecuali 20 yang dipakai jaringan bawaan containerlab).
- `urutan_router`: urutan router RouterOS di lab menurut nama, mulai dari 0. Maksimal 8 router per lab.

Contoh: dengan `winbox_ports: 28000`, router pertama milik pengguna bernomor 3
mendapat port 28000 + 3 × 8 + 0 = **28024**, dan router keduanya 28025. Siswa
tidak perlu menghitung sendiri, karena panel Winbox di halaman lab menampilkan
alamat jadinya.

Rentang yang dipakai selalu 2048 port, mulai dari `winbox_ports` (contoh: 28000
sampai 30047). Port ini di-publish oleh **Docker**, bukan dibuka oleh P-lab sendiri.
Docker memasang aturan iptables-nya sendiri yang dilewati **sebelum** ufw/firewalld,
jadi:

- Tidak perlu `ufw allow` untuk rentang ini; port sudah terjangkau dari LAN begitu lab di-deploy.
- Aturan `ufw allow from <subnet>` atau `ufw deny` **tidak** membatasi port ini. Untuk
  membatasi ke subnet LAN, pakai chain `DOCKER-USER`. Docker sudah mengubah port tujuan
  menjadi 8291 saat paket sampai di chain itu, jadi cocokkan port asli lewat conntrack
  (contoh, sesuaikan subnet dan rentang; belum diuji di semua distro):

  ```bash
  sudo iptables -I DOCKER-USER -p tcp -m conntrack --ctorigdstport 28000:30047 ! -s 192.168.1.0/24 -j DROP
  ```

Setelah mengubah `winbox_ports`, jalankan `sudo systemctl restart p-lab`, lalu
**deploy ulang** lab yang sedang berjalan: port dipasang saat deploy, jadi lab yang
sudah jalan tetap memakai port lama (panel menampilkan port yang benar-benar terbuka).

Langkah siswa:

1. Deploy lab RouterOS, lalu tunggu router selesai boot.
2. Buka panel **Winbox** di halaman lab, dan catat alamat `host:port` tiap router (mis. `192.168.1.10:28024`).
3. Di Winbox, isi **Connect To** dengan alamat itu, lalu login `admin` dengan password `admin`.

> [!WARNING]
> **Catatan keamanan:** port Winbox terbuka untuk **semua komputer di LAN**, bukan
> hanya untuk pemiliknya. Siapa pun di jaringan yang tahu alamat dan port router
> siswa lain bisa membukanya, dan login router masih `admin`/`admin`. Pemisahan
> antar-siswa di level jaringan untuk jalur ini **belum ditangani**. Pakai hanya di
> jaringan yang saling percaya, dan jangan buka ke internet. Kalau tidak perlu,
> biarkan `winbox_ports` kosong dan pakai terminal di web.

## HTTPS (opsional)

P-lab melayani HTTP biasa, jadi password login berjalan tanpa enkripsi di LAN.
Di jaringan yang kamu percaya ini sering dianggap cukup. Kalau ingin HTTPS,
pasang reverse proxy di depannya, lalu di `server.yaml`:

```yaml
listen: 127.0.0.1:8000          # hanya proxy yang bisa mengakses P-lab
allowed_hosts: [lab.sekolah.local]
trusted_proxies: ["127.0.0.1"]  # supaya batas login memakai IP klien asli
```

Proxy harus **meneruskan header `Host` asli** dan **mengisi `X-Forwarded-For`**,
dan harus mendukung WebSocket (terminal lab memakainya).

**Caddy** ([caddyserver.com](https://caddyserver.com)) sudah melakukan semuanya
itu secara bawaan:

```
# /etc/caddy/Caddyfile
lab.sekolah.local {
    tls internal
    reverse_proxy 127.0.0.1:8000
}
```

`tls internal` memakai CA lokal Caddy; browser akan memperingatkan sampai
sertifikat CA-nya dipasang di tiap komputer. Dengan domain publik yang valid,
hapus baris itu dan Caddy mengurus sertifikat sendiri.

**nginx** perlu header dan WebSocket ditulis eksplisit:

```nginx
# /etc/nginx/conf.d/p-lab.conf
map $http_upgrade $connection_upgrade { default upgrade; '' close; }

server {
    listen 443 ssl;
    server_name lab.sekolah.local;
    ssl_certificate     /etc/ssl/certs/lab.crt;
    ssl_certificate_key /etc/ssl/private/lab.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 3600s;   # terminal lab tetap terhubung walau diam
    }
}
```

Setelah itu `sudo systemctl restart p-lab` dan muat ulang proxy-nya
(`caddy` atau `nginx -s reload`).

## Keamanan

Pahami batasannya sebelum membuka ke banyak orang.

- **Node containerlab umumnya berjalan privileged.** Pengguna yang berniat jahat berpotensi keluar dari container dan mengakses mesin server. Mode Server cocok untuk lingkungan yang **saling percaya**: kelas, kantor, tim sendiri. Jangan dipakai untuk publik atau peserta yang tidak dikenal.
- **Isolasi jaringan:** tiap pengguna mendapat jaringan management sendiri, yang dirancang supaya router satu siswa tidak bisa menjangkau router siswa lain (mengandalkan isolasi antar-bridge milik Docker). Ini belum diuji di deploy nyata, jadi cek sendiri di mesinmu: dari CLI router, coba ping IP management router siswa lain. Router tetap bisa menjangkau mesin server (gateway `172.20.n.1`, termasuk port web) serta LAN/internet lewat NAT, dan login router masih `admin/admin`. Ini bukan batas keamanan terhadap pengguna yang berniat jahat (lihat poin pertama).
- **Port Winbox** (kalau `winbox_ports` diisi) berada di luar isolasi ini dan terbuka untuk seluruh LAN: lihat [Winbox dari komputer siswa](#winbox-dari-komputer-siswa).
- **Jangan menjalankan lab mode Pribadi (`./reset.sh` tanpa `LAB_INSTANCE`) di mesin Server:** lab itu memakai jaringan `clab` yang akses luarnya terbuka, sehingga bisa dijangkau router siswa.
- Isi [`allowed_hosts`](#konfigurasi) supaya permintaan dengan `Host` asing ditolak (mencegah DNS rebinding), dan isi `trusted_proxies` kalau memakai proxy.
- Pengguna yang sudah login bisa mengetik command bebas di terminal node lab mereka. Itu memang tujuan lab ini.
- **Jangan buka ke internet**, dan batasi firewall ke LAN.
- Gunakan [HTTPS](#https-opsional) kalau jaringan tidak sepenuhnya kamu percaya.
- Password disimpan sebagai hash scrypt dengan salt per pengguna; token sesi disimpan sebagai hash.
- Jalankan mesin ini khusus untuk P-lab, bukan server yang menyimpan data penting lain.

Seperti di mode Pribadi, grup `clab_admins` dan `docker` praktis setara root
([peringatan](instalasi.md#deploy-lab-tanpa-sudo)). Di mode Server, service
berjalan sebagai `plab`, jadi jangan masukkan akun pengguna biasa ke grup itu.

## Backup dan restore

Yang perlu dicadangkan adalah **`data_dir`** (default `/var/lib/p-lab`): database
akun `p-lab.db` dan arsip sesi semua pengguna. Tambahkan `/etc/p-lab/server.yaml`.

```bash
sudo systemctl stop p-lab
sudo tar czf p-lab-backup-$(date +%F).tar.gz /var/lib/p-lab /etc/p-lab
sudo systemctl start p-lab
```

Berhenti sebentar menjamin database konsisten. Untuk restore, hentikan service,
ekstrak arsipnya ke tempat semula (`sudo tar xzf <file> -C /`), pastikan
pemiliknya `plab` (`sudo chown -R plab: /var/lib/p-lab`), lalu jalankan service.
Lab yang sedang berjalan tidak perlu dicadangkan; deploy ulang saja.

## Migrasi dari mode Pribadi

Beralih dari Pribadi ke Server **sengaja tidak satu klik**, karena mengubah
siapa yang bisa mengakses mesinmu. Urutannya sama dengan [instalasi](#instalasi)
(`--migrate` juga dipakai untuk instalasi baru). Yang khusus untuk peralihan:

- Pre-flight (`--check`) mensyaratkan **tidak ada lab yang sedang berjalan**; hancurkan dulu dengan `./reset.sh` atau `containerlab destroy`.
- Service pribadi (`systemctl --user`) otomatis dihentikan oleh `--migrate` supaya port-nya bebas.
- Riwayat sesi pribadimu **disalin** (bukan dipindah) ke akun admin pertama; yang asli tetap utuh untuk rollback.
- Ringkasan dan cara rollback ditulis ke `<data_dir>/MIGRASI.txt`.

Installer meminta konfirmasi di `--migrate`: kamu harus **mengetik ulang kata
`server`**. Password admin pertama dicetak **sekali** di layar, jadi catat
sebelum menutup terminal.

Selama config mode Server ada di `/etc/p-lab/server.yaml`, `./install.sh` biasa
(tanpa `--server`) **tidak memasang service pribadi** dan memberi peringatan,
supaya service pribadi tidak ikut start sebagai Server. Untuk kembali ke
Pribadi pakai rollback di bawah.

### Rollback

```bash
./install.sh --revert-pribadi
```

Mengembalikan service user dan akses hanya-lokal. Data di `data_dir` **tidak
dihapus**, jadi kamu bisa migrasi lagi nanti tanpa kehilangan akun.

## Masalah umum

| Gejala | Penyebab dan solusi |
|---|---|
| Halaman tidak terbuka dari komputer lain | Cek `listen` (bukan `127.0.0.1`), `systemctl status p-lab`, dan firewall ([akses](#akses-dari-komputer-lain)). |
| `--check` melaporkan port dipakai | Proses lain memakai port itu. Ganti `listen` di `server.yaml`, atau hentikan proses yang memakainya (`ss -ltnp`). |
| `--check` melaporkan KVM tidak ada | Hanya mempengaruhi lab RouterOS. Aktifkan virtualisasi di BIOS/VM, atau tawarkan `net-001` saja. |
| Deploy ditolak: "melebihi batas server" | Perkiraan RAM satu lab sudah lebih dari `capacity.mem_mb`. Minta admin menaikkan batas, atau pilih lab yang lebih kecil. |
| Deploy mengantre lama, atau dibatalkan karena menunggu lebih dari 30 menit | Server sedang penuh. Tunggu lab lain dimatikan (`idle_minutes`), lalu deploy lagi. Naikkan batas kalau RAM memang tersedia ([antrian](#antrian-deploy)). |
| Lab hilang setelah ditinggal sebentar | Dimatikan otomatis setelah `idle_minutes` (halaman lab tertutup dan tidak ada command). Sesi yang belum dinilai tidak bisa dilanjutkan; deploy lagi dan mulai sesi baru. Sesi yang sudah dinilai tetap ada di riwayat. |
| Service gagal start, `Permission denied` di journal | Folder repo tidak bisa dilewati user `plab` ([syarat folder](#syarat-folder-repo)); pindahkan ke `/opt/p-lab` atau `chmod o+x` folder induknya. |
| `p-lab-admin`: "Jalankan: sudo platform/p-lab-admin ..." | Database akun milik `plab`; pakai `sudo`. Jangan menjalankan `p-lab-admin` sebagai root dengan `LAB_DB` diarahkan ke `data_dir`: itu membuat database milik root. |
| Halaman ditolak (Host tidak diizinkan) | Nama/IP yang kamu ketik tidak ada di `allowed_hosts`. Tambahkan lalu restart service. |
| Pengguna lupa password | Admin reset di [dashboard admin](#dashboard-admin), atau `sudo platform/p-lab-admin reset-password <username>`. |
| Login ditolak padahal password benar | Akun mungkin nonaktif: aktifkan lagi di dashboard admin, atau `sudo platform/p-lab-admin list`, lalu `activate <username>`. |
| Muncul permintaan login lagi setelah lama | Sesi login 12 jam. Login ulang; lab yang berjalan tidak terpengaruh. |
| Import CSV: baris gagal | Lihat nomor barisnya. Biasanya username berhuruf besar atau bertitik, atau password kurang dari 8 karakter. |
| Winbox tidak tersambung dari komputer lain | Pastikan `winbox_ports` diisi, lab di-deploy ulang setelah `winbox_ports` diubah, tidak ada aturan `DOCKER-USER` yang memblokir, dan alamat yang dipakai sama dengan yang ada di panel ([Winbox](#winbox-dari-komputer-siswa)). |

## Belum tersedia

Versi ini belum punya fitur berikut. Sementara itu ada jalan keluarnya.

| Fitur | Sementara |
|---|---|
| Hapus akun dari web | nonaktifkan akun di [dashboard admin](#dashboard-admin); data akun dan riwayatnya tetap tersimpan |
| Beberapa kelas per server | satu server untuk satu kelas; kelas lain memakai server terpisah |
