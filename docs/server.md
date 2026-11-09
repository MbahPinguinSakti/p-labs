# Mode Server

[Beranda](../README.md) › Mode Server

Mode Server menjalankan P-lab di satu mesin yang dipakai banyak orang lewat
browser: satu kelas, satu tim IT, atau beberapa orang di rumah. Setiap
pengguna login dengan akunnya sendiri dan mendapat lab sendiri, jadi
kesalahan konfigurasi satu orang tidak mengganggu yang lain.

Kalau kamu hanya memakai P-lab sendirian, tetap di mode Pribadi
([instalasi](instalasi.md#pilih-mode-pribadi-atau-server)).

**Isi halaman:** [Kebutuhan dan sizing](#kebutuhan-dan-sizing) ·
[Instalasi](#instalasi) · [Konfigurasi](#konfigurasi) · [Kapasitas](#batas-kapasitas) · [Key LLM](#key-llm-untuk-nilai-dengan-ai) · [Akun](#akun) ·
[Mandiri vs kelas](#gaya-mandiri-atau-kelas) · [Akses dari komputer lain](#akses-dari-komputer-lain) ·
[HTTPS](#https-opsional) · [Keamanan](#keamanan) · [Backup](#backup-dan-restore) ·
[Migrasi dari Pribadi](#migrasi-dari-mode-pribadi) · [Masalah umum](#masalah-umum) ·
[Belum tersedia](#belum-tersedia)

## Yang berbeda dari mode Pribadi

- Service berjalan sebagai service systemd **system** dengan user `plab`, aktif sejak mesin menyala (tanpa perlu login ke desktop).
- Login wajib. Tidak ada pendaftaran bebas: admin yang membuat akun.
- Tiga role: `admin` (mengelola akun), `guru` (melihat progres siswa di gaya `kelas`), dan `siswa`.
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
```

| Baris | Arti |
|---|---|
| `mode` | `server` untuk mode ini. `pribadi` mengembalikan perilaku lama. |
| `listen` | alamat dan port. `0.0.0.0:8000` bisa diakses dari jaringan; `127.0.0.1:8000` hanya dari mesin itu (cocok kalau di depannya ada reverse proxy). |
| `data_dir` | semua data mode Server: database akun `p-lab.db`, folder `instances/<user>/<lab>/` (lab dan sesi tiap pengguna), dan arsip sesi. Harus bisa ditulis user `plab`. |
| `style` | `mandiri` atau `kelas`, lihat [bagian berikut](#gaya-mandiri-atau-kelas). |
| `capacity.mem_mb` | total estimasi RAM untuk semua lab yang boleh berjalan bersamaan. Deploy ditolak (dengan pesan) kalau perkiraannya melewati batas ini. |
| `capacity.max_deploys` | berapa deploy yang boleh berjalan bersamaan. Deploy lab RouterOS menguras CPU dan disk, jadi 2 biasanya cukup. |
| `capacity.idle_minutes` | lab tanpa aktivitas selama ini (tidak ada command dan halaman lab tidak terbuka) dimatikan untuk membebaskan RAM. Sesi yang belum dinilai **tidak bisa dilanjutkan**: rekamannya disimpan di folder instance, tapi tidak muncul di riwayat. Pengguna perlu deploy lagi dan mulai sesi baru. |
| `allowed_hosts` | opsional tapi **disarankan**: daftar nama host atau IP (yang kamu ketik di browser) yang boleh dipakai membuka P-lab. Permintaan dengan header `Host` lain ditolak; ini mencegah serangan DNS rebinding. Tulis tanpa `http://` dan tanpa port (mis. `[192.168.1.10, lab.sekolah.local]`). Isi semua nama yang dipakai, termasuk IP kalau ada yang membukanya lewat IP. `localhost`, `127.0.0.1`, dan `[::1]` selalu diizinkan supaya admin bisa membuka dari mesin server sendiri. Kosong = semua `Host` diterima (server mencatat peringatan di log). Di mode Pribadi kunci ini tidak boleh diisi. |
| `trusted_proxies` | opsional: IP atau CIDR reverse proxy yang dipercaya. Pembatas percobaan login memakai alamat klien dari `X-Forwarded-For` **hanya** kalau permintaan datang dari alamat di daftar ini; selain itu dipakai alamat koneksi langsung. Daftar yang sama juga menentukan kapan `X-Forwarded-Proto: https` dipercaya untuk memberi flag `Secure` pada cookie login. Isi kalau kamu memasang [proxy HTTPS](#https-opsional), mis. `["127.0.0.1"]`. Proxy wajib meneruskan header `Host` asli; `X-Forwarded-Host` tidak dibaca. |

Setelah mengubah file ini: `sudo systemctl restart p-lab`.

## Batas kapasitas

Tanpa batas, 30 siswa yang menekan Deploy bersamaan akan membuat mesin hang.
Karena itu P-lab membatasi lewat beberapa aturan, sebagian dari `capacity` di config:

- **RAM (`mem_mb`)**: sebelum deploy, P-lab menjumlahkan perkiraan RAM lab yang sedang berjalan (dari `resources.mem_mb` di `problem.yaml` tiap lab). Kalau lab baru membuat totalnya melewati `mem_mb`, deploy **ditolak dengan pesan**. Pengguna mencoba lagi nanti.
- **Deploy bersamaan (`max_deploys`)**: hanya sejumlah ini yang boleh berjalan sekaligus. Deploy lain diminta **mencoba lagi** sebentar.
- **Satu lab per pengguna**: men-deploy lab baru mematikan lab lain milik pengguna yang sama. Siswa tidak bisa memegang beberapa lab sekaligus.
- **Tanpa aktivitas (`idle_minutes`)**: lab yang tidak disentuh selama itu dimatikan untuk membebaskan RAM. Halaman lab yang masih terbuka di browser dihitung sebagai aktivitas. Sesi yang belum dinilai tidak bisa dilanjutkan dan tidak muncul di riwayat, jadi ingatkan pengguna menekan **Selesai & nilai** sebelum pergi.
- **Akun dinonaktifkan**: lab milik akun itu ikut dimatikan.

Tidak ada antrian otomatis: penolakan hanya memberi pesan, bukan menunggu giliran.

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

Akun dikelola lewat CLI `platform/p-lab-admin`, dijalankan di mesin server.
Tidak ada registrasi bebas. **Selalu pakai `sudo`**: database akun milik user `plab`
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

## Gaya mandiri atau kelas

Diatur lewat `style` di config.

| | `mandiri` | `kelas` |
|---|---|---|
| Hubungan antar pengguna | semua setara | guru dan siswa |
| Leaderboard | ada; semua pengguna tampil dengan nama | ada, anonim: siswa melihat teman sebagai "Siswa lain", guru dan admin melihat nama |
| Guru | tidak ada peran khusus | melihat progres semua siswa |
| Cocok untuk | tim IT, komunitas, belajar bareng | kelas dengan guru yang menilai |

Di kedua gaya, siswa hanya melihat sesi dan hasilnya sendiri. API progres kelas
(`/api/class/progress`) sudah ada, tetapi halaman dashboard guru di web
[belum tersedia](#belum-tersedia).

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
di mode Pribadi (lihat [Memakai Winbox](penggunaan.md#memakai-winbox)). Namun
akses Winbox per pengguna dari jaringan **belum tersedia**: alamat router ada di
jaringan Docker server. Sementara ini pengguna memakai terminal di web.

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
| Deploy ditolak karena kapasitas penuh | Total `capacity.mem_mb` terpakai. Tunggu lab lain dimatikan (`idle_minutes`), atau naikkan batas kalau RAM memang tersedia. |
| Lab hilang setelah ditinggal sebentar | Dimatikan otomatis setelah `idle_minutes` (halaman lab tertutup dan tidak ada command). Sesi yang belum dinilai tidak bisa dilanjutkan; deploy lagi dan mulai sesi baru. Sesi yang sudah dinilai tetap ada di riwayat. |
| Service gagal start, `Permission denied` di journal | Folder repo tidak bisa dilewati user `plab` ([syarat folder](#syarat-folder-repo)); pindahkan ke `/opt/p-lab` atau `chmod o+x` folder induknya. |
| `p-lab-admin`: "Jalankan: sudo platform/p-lab-admin ..." | Database akun milik `plab`; pakai `sudo`. Jangan menjalankan `p-lab-admin` sebagai root dengan `LAB_DB` diarahkan ke `data_dir`: itu membuat database milik root. |
| Halaman ditolak (Host tidak diizinkan) | Nama/IP yang kamu ketik tidak ada di `allowed_hosts`. Tambahkan lalu restart service. |
| Pengguna lupa password | `sudo platform/p-lab-admin reset-password <username>`. |
| Login ditolak padahal password benar | Akun mungkin nonaktif: `sudo platform/p-lab-admin list`, lalu `activate <username>`. |
| Muncul permintaan login lagi setelah lama | Sesi login 12 jam. Login ulang; lab yang berjalan tidak terpengaruh. |
| Import CSV: baris gagal | Lihat nomor barisnya. Biasanya username berhuruf besar atau bertitik, atau password kurang dari 8 karakter. |

## Belum tersedia

Versi ini belum punya fitur berikut. Sementara itu ada jalan keluarnya.

| Fitur | Sementara |
|---|---|
| Dashboard admin di web (kelola user, lihat lab yang berjalan) | pakai `platform/p-lab-admin`; lab berjalan dilihat lewat `docker ps` atau `sudo containerlab inspect --all` |
| Halaman dashboard guru untuk gaya `kelas` | API `/api/class/progress` sudah ada, halaman web belum; guru memakai akun biasa |
| Antrian otomatis saat kapasitas penuh | deploy yang melewati batas ditolak dengan pesan; pengguna mencoba lagi sendiri |
| Akses Winbox per pengguna dari jaringan | pakai terminal di web (perubahan lewat Winbox yang sudah ada tetap dinilai) |
