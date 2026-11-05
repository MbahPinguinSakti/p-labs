# Evaluasi net-001 · sesi 20261103-023553

**Skor akhir: 56.2**

| Dimensi | Skor | Bobot | Dasar |
|---|---|---|---|
| correctness | 50 | 30% | sw2: vlan_filtering=0; sw2:eth2 tidak membawa VLAN 20 |
| efficiency | 100 | 20% | 1 perubahan (baseline 1), 0 rework |
| methodology | 48 | 40% | campuran |
| safety | 50 | 10% | disable_vlan_filtering (major) |

Penalti hint: -3 (level [1])

## Checkpoint

- ✓ `diagnose` pada `E2` sw2: `bridge vlan show`
- ✓ `locate_fault` pada `E2` sw2: `bridge vlan show`
- · `apply_fix`
- · `verify_fix`
- · `reasoning` (LLM): Pemain tidak pernah membentuk hipotesis eksplisit tentang VLAN/trunk sebelum mengubah config. Urutan command menunjukkan: temukan data (E2, E3, E4) → langsung ubah config (E5) tanpa ada langkah atau output yang menunjukkan pemain menyimpulkan 'VLAN 20 hilang dari trunk eth2 di sw2, jadi saya perlu menambahkannya'. Fix yang dipilih (mematikan vlan_filtering) juga tidak konsisten dengan hipotesis VLAN-missing yang seharusnya muncul dari pembacaan E2, sehingga tidak ada indikasi hipotesis yang benar pernah terbentuk.

## Feedback

Kamu menemukan fault dengan sangat cepat — output `bridge vlan show` di sw2 pada menit pertama sudah menunjukkan root cause dengan jelas. Sayangnya, kamu tidak membaca output itu sampai tuntas, membuka hint yang tidak diperlukan, dan akhirnya menerapkan fix yang salah (mematikan vlan_filtering) yang merusak isolasi VLAN di seluruh sw2. Ping berhasil, tapi desain jaringan rusak — itulah kenapa correctness hanya 50 dan safety kena penalti major.

**Yang sudah bagus**

- Langsung ke sw2 dan menjalankan `bridge vlan show` di menit pertama (E2) — ini pilihan yang tepat dan efisien. Kamu membaca topologi dan menentukan titik yang paling mungkin bermasalah dengan benar.
- Melakukan verifikasi akhir dengan ping dari host-a (E6) setelah menerapkan fix — kebiasaan ini benar dan harus dipertahankan.

**Yang perlu diperbaiki**

1. **Baca output sebelum lanjut.** Di E2, `bridge vlan show` di sw2 sudah menampilkan: eth2 hanya punya VLAN 10, sementara eth1 punya VLAN 10 dan 20. Ini adalah fault yang lengkap dan actionable. Fix-nya langsung: `bridge vlan add dev eth2 vid 20 trunk`. Jangan pindah ke perangkat lain atau buka hint sebelum kamu benar-benar membaca semua baris output.
2. **Jangan gunakan `vlan_filtering=0` sebagai troubleshooting tool.** Mematikan vlan_filtering tidak 'memperbaiki' VLAN yang hilang — ia hanya menghapus seluruh filtering sehingga semua traffic bebas lewat tanpa isolasi. Ini setara dengan mencabut firewall untuk memperbaiki rule yang salah. Root cause-nya adalah entry VLAN yang hilang, bukan filtering yang aktif.
3. **Tunda hint sampai kamu benar-benar buntu.** Kamu membuka H1 (E+01:09) padahal fault sudah terlihat di E2 (E+00:29). Kebiasaan ini mengurangi nilai dan, lebih penting, melatih kamu untuk bergantung pada petunjuk alih-alih membaca output. Paksa dirimu untuk mengeksekusi setidaknya satu langkah lanjutan dari setiap output sebelum membuka hint.
4. **Bedakan antara 'bridge parameter' dan 'VLAN membership'.** `ip -d link show br0` (E4) menampilkan parameter bridge secara keseluruhan — vlan_filtering=1 di situ adalah kondisi normal dan benar. Yang salah adalah VLAN membership per-port, yang sudah terlihat di `bridge vlan show` (E2). Dua command ini menampilkan layer informasi yang berbeda.

**Pelajaran teknis**

- `bridge vlan show` menampilkan VLAN yang diizinkan per port. Kalau sebuah port trunk seharusnya membawa VLAN 10 dan 20, tapi hanya terlihat VLAN 10, fix-nya adalah `bridge vlan add dev <port> vid <vlan> trunk` — bukan mengubah parameter bridge.
- Mematikan `vlan_filtering` di Linux bridge (`ip link set br0 type bridge vlan_filtering 0`) menghapus seluruh isolasi VLAN: semua port di bridge akan berada dalam satu broadcast domain. Ini bukan fix untuk VLAN yang hilang, ini adalah penghapusan mekanisme VLAN secara keseluruhan.

**Momen penting**

- `E2` sw2: `bridge vlan show`: Momen paling menentukan: `bridge vlan show` di sw2 sudah menunjukkan eth2 hanya punya VLAN 10. Root cause ditemukan di sini, kurang dari 30 detik. Sesi bisa selesai di menit pertama kalau output ini dibaca sampai tuntas.
- `H1` host: `(hint level 1 dibuka)`: Pemain membuka hint 40 detik setelah menemukan fault — menunjukkan output E2 tidak dibaca dengan seksama, atau pemain tidak yakin dengan apa yang dilihat.
- `E4` sw2: `ip -d link show br0`: Memeriksa `ip -d link show br0` dan melihat vlan_filtering=1. Kemungkinan besar ini yang memicu keputusan di E5 — pemain salah menginterpretasikan parameter normal sebagai penyebab masalah.
- `E5` sw2: `ip link set br0 type bridge vlan_filtering 0`: Titik kegagalan utama: `ip link set br0 type bridge vlan_filtering 0` adalah fix yang salah untuk masalah yang sudah terdiagnosis. Satu perubahan ini menyebabkan safety violation major dan membuat desain jaringan rusak meski ping akhirnya berhasil.
- `E6` host-a: `ping -c 3 -W 1 10.20.0.2`: Ping berhasil — tapi karena vlan_filtering dimatikan, bukan karena VLAN 20 diperbaiki. Verifikasi fungsional saja tidak cukup; kamu juga harus verifikasi bahwa VLAN isolation masih bekerja.

**Latihan berikutnya:** Di soal berikutnya, setelah menjalankan command diagnostik apapun, paksa dirimu untuk menuliskan (atau setidaknya menyebutkan dalam pikiran) satu kalimat: 'Dari output ini, saya simpulkan bahwa X salah, dan fix-nya adalah Y.' Kalau kamu tidak bisa melengkapi kalimat itu, berarti kamu belum selesai membaca output — jangan jalankan command berikutnya dulu.

## Penilaian methodology

campuran · 48

Pemain memulai dengan benar: ping di host-a untuk konfirmasi masalah (E1), lalu langsung ke sw2 untuk cek `bridge vlan show` (E2). Output E2 sudah jelas menunjukkan fault — eth2 di sw2 hanya punya VLAN 10, tanpa VLAN 20. Ini adalah temuan kritis yang seharusnya langsung memicu `bridge vlan add dev eth2 vid 20`. Namun pemain tidak menindaklanjuti bukti tersebut: membuka hint H1, lalu berpindah ke sw1 untuk melakukan perbandingan (E3, langkah yang wajar tapi tidak diperlukan karena fault sudah terlihat di E2). Setelah kembali ke sw2 dan memeriksa detail bridge (E4, yang menunjukkan vlan_filtering=1 — normal), pemain memilih fix yang salah: mematikan vlan_filtering di seluruh bridge (E5) alih-alih menambahkan VLAN 20 ke eth2. Fix ini membuat ping berhasil (E6) tapi merusak isolasi VLAN — semua traffic kini berada di satu broadcast domain, menyebabkan violation safety major. Kesimpulan: diagnosis awal sangat baik (fault ditemukan di E2), tapi eksekusi fix adalah trial-and-error karena pemain mengabaikan bukti yang sudah ada dan memilih pendekatan 'matikan filtering' tanpa hipotesis yang valid.

- `E2` sw2: `bridge vlan show`: Output `bridge vlan show` di sw2 sudah jelas: eth2 hanya punya VLAN 10, tidak ada VLAN 20. Ini adalah root cause yang lengkap — pemain melihatnya tapi tidak bertindak.
- `H1` host: `(hint level 1 dibuka)`: Pemain membuka hint padahal fault sudah terlihat di E2. Menunjukkan kurangnya kepercayaan diri dalam membaca output yang sudah ada.
- `E3` sw1: `bridge vlan show`: Cek sw1 untuk perbandingan — langkah ini reasonable tapi tidak diperlukan karena fault sudah terlokasi di sw2/eth2 sejak E2.
- `E4` sw2: `ip -d link show br0`: `ip -d link show br0` menampilkan vlan_filtering=1 (normal). Pemain kemungkinan salah mengartikan ini sebagai sumber masalah, memicu fix yang salah di E5.
- `E5` sw2: `ip link set br0 type bridge vlan_filtering 0`: Mematikan vlan_filtering adalah perubahan tanpa dasar hipotesis yang valid. Fix yang benar (`bridge vlan add dev eth2 vid 20`) sudah bisa disimpulkan sejak E2. Ini menyebabkan safety violation major.

_Methodology dari 3 run: [48, 48, 48] (median 48)_
