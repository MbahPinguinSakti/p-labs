# Evaluasi net-001 · sesi 20261103-012346

**Skor akhir: 12.0**

| Dimensi | Skor | Bobot | Dasar |
|---|---|---|---|
| correctness | 100 → 0.0 | 30% | ping OK |
| efficiency | 100 → 0.0 | 20% | 1 perubahan (baseline 1), 0 rework |
| methodology | 5 | 40% | tanpa_metode |
| safety | 100 | 10% | tidak ada pelanggaran |

Process gate ×0.0: correctness, efficiency hanya dikreditkan sebagian, karena checkpoint proses ['diagnose', 'locate_fault'] tidak tercapai sebelum `apply_fix`.

## Checkpoint

- · `diagnose`
- · `locate_fault`
- ✓ `apply_fix` pada `E1` sw2: `bridge vlan add dev eth2 vid 20`
- ✓ `verify_fix` pada `E2` host-a: `ping -c 3 -W 1 10.20.0.2`
- · `reasoning` (LLM): Tidak ada evidence dalam timeline yang menunjukkan pemain membentuk hipotesis tentang VLAN/trunk sebelum mengubah konfigurasi. Sesi hanya terdiri dari 2 event: langsung fix di E1, lalu verifikasi di E2. Tidak ada command diagnostik, tidak ada output yang menunjukkan pemain memeriksa status VLAN/trunk, dan tidak ada narasi atau langkah yang mengindikasikan reasoning eksplisit maupun implisit.

## Feedback

Kamu berhasil memperbaiki fault dengan tepat dan efisien—satu perubahan state, nol pelanggaran safety, dan konektivitas pulih sepenuhnya. Tapi sesi ini tidak memiliki proses troubleshooting sama sekali: kamu langsung tahu jawabannya (atau menebak dengan sangat tepat) dan mengeksekusinya tanpa satu pun langkah diagnostik. Di skenario nyata dengan lebih banyak variabel, pendekatan ini berbahaya karena tidak bisa diulang jika tebakan meleset.

**Yang sudah bagus**

- Fix yang diterapkan di E1 (`bridge vlan add dev eth2 vid 20` di sw2) adalah solusi yang 100% benar dan minimal—tepat satu perubahan sesuai baseline expert.
- Verifikasi end-to-end dilakukan dengan ping di E2, membuktikan konektivitas VLAN 20 pulih tanpa perlu alat tambahan.

**Yang perlu diperbaiki**

1. Mulai setiap sesi dengan diagnosis end-to-end dulu. Sebelum menyentuh config apa pun, jalankan `ping 10.20.0.2` dari host-a untuk mengonfirmasi fault, lalu `bridge vlan show` di sw1, sw2, sw3 untuk memetakan state VLAN saat ini. Tanpa langkah ini, kamu tidak bisa membedakan 'tahu' dari 'menebak'.
2. Isolasi fault secara sistematis sebelum fix. Setelah melihat output `bridge vlan show`, kamu seharusnya bisa menunjuk baris yang hilang—misalnya VLAN 20 tidak muncul di eth2 sw2—dan baru kemudian mengeksekusi fix. Ini yang dimaksud `locate_fault` dalam checkpoint yang tidak terpenuhi.
3. Jangan skip reasoning eksplisit. Bahkan jika kamu sudah tahu jawabannya, biasakan menuliskan (atau setidaknya menjalankan command yang membuktikan) hipotesis: 'trunk sw2 kemungkinan kehilangan VLAN 20, cek dulu sebelum ubah.' Ini membuat pendekatanmu bisa dipertanggungjawabkan dan diaudit.
4. Verifikasi management VLAN juga. Tiket menyebut agar trunk VLAN 10 dan management switch tidak terganggu. Setelah fix, idealnya kamu juga mengecek bahwa sw1, sw2, sw3 masih bisa saling ping via vlan10—meski dalam kasus ini fixnya memang tidak menyentuh VLAN 10.

**Pelajaran teknis**

- Pada Linux bridge dengan `vlan_filtering`, allowed VLAN per-port dikonfigurasi secara eksplisit dengan `bridge vlan add/del`. `bridge vlan show` adalah command kunci untuk melihat state ini—keluarannya menampilkan setiap port beserta VLAN yang diizinkan, sehingga kamu bisa langsung melihat VLAN yang hilang tanpa perlu tebak-tebakan.
- Process gate dalam penilaian ini mengukur apakah ada bukti diagnosis sebelum fix. Correctness dan efficiency kamu sempurna, tapi keduanya di-gate oleh proses—artinya skor final bisa dikurangi kalau sistem menilai proses sebagai syarat. Biasakan menjalankan command diagnostik yang terdokumentasi agar proses kamu bisa diverifikasi.

**Momen penting**

- `E1` sw2: `bridge vlan add dev eth2 vid 20`: Fix dijalankan di detik pertama tanpa diagnostik apapun. Ini adalah momen yang menentukan seluruh karakter sesi—benar secara hasil, tapi absen secara proses.
- `E2` host-a: `ping -c 3 -W 1 10.20.0.2`: Verifikasi dengan ping adalah satu-satunya langkah observasi dalam sesi, dan dilakukan setelah fix. Hasilnya benar (0% packet loss), membuktikan fault teratasi—tapi urutan yang ideal adalah observasi → hipotesis → fix → verifikasi.

**Latihan berikutnya:** Di soal berikutnya, wajibkan dirimu menjalankan minimal 3 command diagnostik dan membaca outputnya sebelum mengubah satu pun konfigurasi—catat perangkat mana yang bermasalah dan baris output mana yang membuktikannya, baru kemudian eksekusi fix.

## Penilaian methodology

tanpa_metode · 5

Pemain langsung mengeksekusi fix (`bridge vlan add dev eth2 vid 20` di sw2) di detik pertama sesi tanpa satu pun command diagnostik sebelumnya. Tidak ada `bridge vlan show`, `ping`, `ip link`, atau command lain yang dijalankan untuk mengumpulkan bukti. Checkpoint `diagnose` dan `locate_fault` tidak terpenuhi, dan process gate mengembalikan factor 0.0. Meski hasil akhirnya benar dan efisien secara state changes, proses yang dijalani tidak mencerminkan troubleshooting—ini adalah pengetahuan langsung tentang fault (atau tebakan yang sangat tepat) tanpa metodologi yang bisa dipertanggungjawabkan.

- `E1` sw2: `bridge vlan add dev eth2 vid 20`: Fix (`bridge vlan add dev eth2 vid 20`) dijalankan 1 detik setelah sesi mulai, tanpa satu pun command diagnostik sebelumnya. Tidak ada bukti bahwa fault diidentifikasi melalui observasi.
- `E2` host-a: `ping -c 3 -W 1 10.20.0.2`: Verifikasi dengan ping dilakukan dan berhasil, yang merupakan langkah yang benar—tetapi ini adalah satu-satunya langkah diagnostik dalam sesi, dan dilakukan setelah fix, bukan sebelum.

_Methodology dari 3 run: [5, 5, 5] (median 5)_
