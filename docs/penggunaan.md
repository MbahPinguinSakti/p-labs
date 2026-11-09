# Penggunaan

[Beranda](../README.md) › Penggunaan

Buka **http://localhost:8000**, atau klik ikon **P-lab** di menu aplikasi. Kalau
halaman tidak terbuka, cek service-nya dengan `systemctl --user status p-lab`
(lihat [instalasi](instalasi.md#service-web-ui)).

> [!NOTE]
> Di [mode Server](server.md), alamatnya adalah alamat mesin server
> (mis. `http://192.168.1.10:8000`) dan kamu harus **login** dulu dengan akun
> dari admin. Sesi login berlaku 12 jam. Setiap pengguna punya lab, sesi,
> progres, dan hasil sendiri; langkah di bawah sama saja.

Menu di sidebar mengikuti role akunmu. **Siswa** melihat menu biasa (Home, Progress,
Labs, dan seterusnya). **Guru** di gaya `kelas` melihat menu **Progres kelas**
([halaman kelas](server.md#halaman-kelas)). **Admin** melihat **Akun** dan
**Lab berjalan** ([dashboard admin](server.md#dashboard-admin)), ditambah
**Progres kelas** di gaya `kelas`.

**Isi halaman:** [Alur satu sesi](#alur-satu-sesi) · [Cara skor dihitung](#cara-skor-dihitung) ·
[Membaca hasil](#membaca-hasil) · [Mode terminal](#mode-terminal-tanpa-web-ui) ·
[Penyimpanan data](#di-mana-data-disimpan)

## Alur satu sesi

```
 1 Pilih lab ─▶ 2 Deploy & mulai ─▶ 3 Diagnosis & perbaiki ─▶ 4 Hint (opsional) ─▶ 5 Selesai & nilai ─▶ Baca hasil
```

### 1. Pilih lab

**Home** menampilkan lab unggulan dan ringkasan progresmu. **Labs** berisi
semua soal, dengan filter kategori dan kesulitan. Lab bertanda *segera hadir*
belum punya soal, jadi belum bisa dimainkan.

### 2. Mulai sesi

Halaman lab menampilkan tiket, topologi, dan riwayat sesi sebelumnya. Tombol
yang muncul tergantung keadaan lab:

| Keadaan | Tombol |
|---|---|
| Lab belum berjalan | **Deploy & mulai**. Prosesnya sekitar 30 detik dan progresnya tampil per tahap: membersihkan lab lama, menyalakan node, memeriksa lab sehat, lalu memasang fault. |
| Lab berjalan dan sehat | **Mulai sesi**. Fault langsung dipasang ulang, tanpa deploy. |
| Lab berjalan tapi rusak | **Mulai sesi** ditolak, lalu muncul **Deploy ulang lab**. |

Kalau deploy dari web belum diaktifkan ([instalasi](instalasi.md#deploy-lab-tanpa-sudo)),
halaman menampilkan perintah yang harus dijalankan di terminal:
`cd labs/<id> && ./reset.sh`.

Di [mode Server](server.md), kalau server sedang penuh, Deploy masuk **antrian**.
Halaman lab menampilkan posisimu dan tombol **Batalkan antrian**. Antrian dibatalkan
otomatis setelah 30 menit ([detail](server.md#antrian-deploy)).

### 3. Kerjakan soalnya

Layar sesi terbagi tiga:

- **Kiri**: tiket, checkpoint, dan hint.
- **Tengah**: terminal. Ada satu tab per node, dan kamu juga bisa membuka
  terminal dengan mengklik node di diagram topologi. Shell di tiap tab tetap
  hidup saat kamu berpindah tab.
- **Kanan**: topologi dan aktivitas, yaitu command terakhir beserta ID event-nya
  (`E12`).

Beberapa hal yang perlu kamu tahu:

- **Semua command direkam**, termasuk outputnya. Command baca (`show`, `ping`,
  `ip a`) tidak mengurangi skor efficiency. Yang dihitung hanya command yang
  mengubah state.
- **Checkpoint** menyala otomatis begitu kamu mencapainya, misalnya "Diagnosis
  awal" atau "Terapkan perbaikan". Checkpoint tertentu tampil sebagai
  *Checkpoint tersembunyi* karena namanya bisa membocorkan lokasi fault. Isinya
  baru terlihat setelah sesi dinilai.
- **Timer** mulai berjalan sejak command pertama, bukan sejak halaman dibuka.
- **Reset lab** membuang sesi ini tanpa menilainya, lalu men-deploy ulang dari
  awal. Pakai ini kalau lab-nya sudah terlalu berantakan.

### Router MikroTik RouterOS

Di lab RouterOS (net-002, net-003), terminal router berupa **shell RouterOS**
dengan prompt seperti di perangkat aslinya: `[admin@r2] /ip address>`.

- Command bisa diketik dengan path lengkap (`/ip address print`), atau masuk ke
  menu dulu (`/ip address`, lalu `print`). `..` naik satu menu, `/` kembali ke
  root, dan Tab melengkapi nama menu.
- `ping`, `traceroute`, dan `monitor` otomatis dibatasi (`count=4`, `once`)
  supaya selesai sendiri. Tambahkan `count=` sendiri kalau perlu jumlah lain.
- Scripting RouterOS (`:put [...]`, `:foreach`) juga bisa dipakai.
- `quit` menutup shell.

Shell ini adalah proxy di komputermu yang mengirim setiap command ke router
lewat SSH, karena RouterOS tidak bisa dipasangi perekam seperti host Linux.
Akibatnya, mode interaktif khusus RouterOS (editor `edit`, `/system console`,
Safe Mode dengan Ctrl-X) tidak tersedia.

#### Memakai Winbox

Router juga bisa dikonfigurasi lewat **Winbox** (atau WebFig). Selama sesi,
panel **Winbox** di halaman sesi menampilkan alamat tiap router
(mis. `172.20.20.3:8291`, login `admin`/`admin`).

- Di [mode Server](server.md#winbox-dari-komputer-siswa) dengan Winbox dari komputer
  lain diaktifkan, panel menampilkan `alamat-server:port` yang bisa langsung kamu
  buka dari komputermu sendiri.
- Di mode Pribadi, alamat itu ada di jaringan Docker mesin lab. Dari komputer lain,
  buka tunnel dulu: `ssh -L 8291:172.20.20.3:8291 <mesin-lab>`, lalu sambungkan
  Winbox ke `127.0.0.1`.
- Setiap **perubahan** dari Winbox direkam: P-lab membandingkan konfigurasi
  router tiap ±3 detik dan mencatat selisihnya sebagai command RouterOS,
  dengan label `winbox` di daftar aktivitas. Perubahan itu dinilai seperti
  command terminal (efficiency, safety, checkpoint).
- Yang **tidak** terekam: aktivitas membaca. Membuka tabel IP › Addresses di
  Winbox tidak meninggalkan jejak, jadi checkpoint diagnosis tidak tercapai.
  Kalau perbaikannya dibuat lewat Winbox, process gate tidak diterapkan (lihat
  [Cara skor dihitung](#cara-skor-dihitung)). Evaluator LLM diberi tahu
  keterbatasan ini dan tidak memberi band methodology tertinggi, karena
  prosesnya tidak teramati.

Mau proses diagnosismu ikut dinilai? Lakukan pengecekan di terminal (mis.
`/ip address print`), lalu boleh tetap memperbaiki lewat Winbox.

### 4. Hint

**Minta hint** membuka hint level berikutnya. Setiap level memotong skor akhir
(di net-001: level 1 = 3 poin, level 2 = 7 poin). Hint harus dibuka berurutan.
Membaca ulang hint yang sudah dibuka tidak menambah potongan.

### 5. Selesai & nilai

Ada dua pilihan:

- **Nilai dengan AI**: semua dimensi dinilai, termasuk methodology, dan skor
  akhir dihitung. Prosesnya biasanya 30–90 detik. Butuh provider LLM
  ([instalasi](instalasi.md#evaluator-ai)).
- **Nilai tanpa AI**: correctness, efficiency, dan safety tetap dihitung, tapi
  methodology dan skor akhir dikosongkan.

Setelah dinilai, sesi ditutup dan diarsipkan ke `labs/<id>/sessions/<sesi>/`.
Terminal masih bisa dipakai, tapi command berikutnya tidak dinilai lagi.

## Cara skor dihitung

| Dimensi | Siapa yang menilai | Isinya |
|---|---|---|
| **Correctness** | `verify.sh` (otomatis) | 100 = masalah selesai dan desain utuh, 50 = masalah selesai tapi lewat jalan pintas yang merusak desain, 0 = belum selesai |
| **Efficiency** | rumus | 100, dikurangi 15 per perubahan state di atas baseline expert, dan dikurangi 10 per perubahan yang diulang pada objek yang sama (trial-and-error) |
| **Methodology** | AI | urutan kerja: gejala → hipotesis → isolasi → perbaikan terukur → verifikasi. Setiap penilaian wajib mengutip event (`E5`, `E12`) |
| **Safety** | aturan per soal | 100, dikurangi 25 per pelanggaran minor dan 50 per pelanggaran major, misalnya mengubah port sehat atau mematikan fitur pengaman |

Rumus skor akhir:

```
skor akhir = Σ bobot × dimensi − potongan hint
```

Bobotnya diatur per soal. Di net-001 bobotnya: correctness 30%, efficiency 20%,
methodology 40%, safety 10%.

**Process gate**: correctness dan efficiency hanya dihitung penuh kalau kamu
terbukti mendiagnosis *sebelum* memperbaiki. Kalau kamu langsung memperbaiki
tanpa melihat apa pun, keduanya dikali 0. Tujuannya supaya menebak lalu
kebetulan benar tidak mengalahkan kerja yang sistematis.
Pengecualian: kalau perbaikan dibuat lewat Winbox, gate tidak diterapkan,
karena diagnosis di Winbox memang tidak bisa direkam. Hasilnya diberi catatan
"mode GUI".

## Membaca hasil

Halaman **Hasil Evaluasi** berisi:

- skor akhir dan band methodology (`sistematis`, `campuran`, `trial_and_error`, `tanpa_metode`);
- nilai tiap dimensi, termasuk nilai sebelum dan sesudah process gate;
- **momen kunci**: command yang paling menentukan, dengan penjelasan dari AI;
- semua checkpoint, termasuk yang tadinya tersembunyi;
- feedback dan pelanggaran safety, masing-masing dengan rujukan event;
- **timeline lengkap**: setiap command dengan output-nya. Command yang mengubah
  state dan yang merupakan rework ditandai.

**Progress** menampilkan points (jumlah skor terbaik per lab, jadi mengulang lab
tidak menambah poin) dan tren methodology. **Leaderboard** mode lokal
membandingkan skormu dengan golden transcript bawaan soal, misalnya *expert*
dan *nyontek*. **Belajar** berisi materi singkat per topik beserta lab
latihannya.

## Mode terminal (tanpa web UI)

Semua bisa dikerjakan dari terminal biasa. Ini berguna di server tanpa browser,
atau saat membuat soal.

```bash
cd labs/net-001
./reset.sh                                   # deploy + inject → sesi baru
../../platform/lab-shell . host-a            # masuk ke node (direkam)
../../platform/lab-hint .                    # buka hint berikutnya
../../platform/checkpoints.py status .       # checkpoint yang sudah tercapai
./verify.sh                                  # cek correctness kapan saja
../../platform/evaluate.py run .             # nilai sesi (pakai env LLM)
../../platform/evaluate.py run . --dry-run   # tanpa LLM: tulis prompt evaluator saja
```

Kalau memakai `lab-shell` dari terminal, checkpoint watcher tidak berjalan
otomatis. Jalankan `../../platform/serve .`, yang menyalakan ttyd + watcher di
:7681, atau biarkan web UI yang menjalankannya.

Hasil evaluasi CLI ditulis ke `.state/evaluation.json` dan
`.state/evaluation.md` (laporan yang bisa dibaca).

## Di mana data disimpan

| Lokasi | Isi |
|---|---|
| `labs/<id>/.state/` | sesi yang sedang berjalan (rekaman, checkpoint, ground truth) |
| `labs/<id>/sessions/<sesi>/` | arsip sesi yang sudah dinilai, dibaca halaman Progress dan Hasil |
| `labs/<id>/golden/<sesi>/` | golden transcript bawaan soal (untuk leaderboard dan menguji evaluator) |
| `~/.config/p-lab/web.env` | konfigurasi provider LLM |

Semuanya lokal. Satu-satunya data yang keluar dari komputermu adalah prompt
evaluator: transcript sesi dan ground truth soal yang dikirim ke provider LLM
yang kamu pilih. Kalau ingin semuanya tetap offline, pakai LLM lokal.
