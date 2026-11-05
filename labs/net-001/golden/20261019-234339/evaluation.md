# Evaluasi net-001 · sesi 20261019-234339

**Skor akhir: 38.0**

| Dimensi | Skor | Bobot | Dasar |
|---|---|---|---|
| correctness | 50 | 30% | sw1:eth1 (port akses) bukan access VLAN 20 murni: vlans=[10, 20] flags20=['Egress Untagged', 'PVID'] |
| efficiency | 0 | 20% | 9 perubahan (baseline 1), 5 rework |
| methodology | 45 | 40% | campuran |
| safety | 50 | 10% | touch_access_port (minor), mgmt_vlan_to_user_port (minor) |

## Checkpoint

- ✓ `diagnose` pada `E3` sw2: `bridge -d vlan`
- ✓ `locate_fault` pada `E3` sw2: `bridge -d vlan`
- ✓ `apply_fix` pada `E96` sw2: `bridge vlan add dev eth2 vid 20`
- ✓ `verify_fix` pada `E150` host-a: `ping 10.20.0.2`
- ✓ `reasoning` (LLM): Pemain menunjukkan hipotesis tentang VLAN/trunk sebelum melakukan perubahan config. Pada E3, pemain langsung mengecek `bridge -d vlan` di sw2 sebagai langkah pertama setelah melihat topologi, dan output-nya menunjukkan pemain sudah tahu bahwa masalah kemungkinan ada di allowed VLAN pada trunk. Setelah melihat VLAN 20 tidak ada di eth2 sw2, pemain berusaha menambahkannya (meski pada perangkat yang salah di awal, E23). Urutan ini—cek VLAN table dulu, lalu tambah VLAN yang hilang—mencerminkan hipotesis yang jelas: 'VLAN 20 tidak diizinkan melewati trunk tertentu'. Hipotesis ini benar secara konsep meski eksekusinya salah sasaran.

## Feedback

Kamu menemukan fault dalam waktu 31 detik dengan satu command yang tepat—`bridge -d vlan` di sw2 langsung menunjukkan VLAN 20 tidak ada di eth2. Itu hasil diagnosis yang sangat baik. Sayangnya, setelah temuan itu kamu kehilangan arah: fix diterapkan ke perangkat yang salah (sw3 bukan sw2), port akses yang sehat ikut diubah berulang kali, dan sesi yang seharusnya selesai dalam 8 menit berlarut sampai 54 menit dengan 9 perubahan state (baseline: 1). Ping akhirnya berhasil, tapi ada sisa kerusakan di sw1/eth1 yang tidak bersih (VLAN 10 di port akses user).

**Yang sudah bagus**

- Diagnosis awal sangat tepat sasaran: langsung ke `bridge -d vlan` di sw2 (E3) tanpa membuang waktu, dan output-nya sudah secara eksplisit menunjukkan eth2 sw2 hanya punya VLAN 10—fault sudah terlokasi dalam 31 detik pertama.
- Verifikasi konsisten dilakukan setelah setiap perubahan (E24, E99, E103, E127, E139, E146), menunjukkan kebiasaan yang benar meski tindak lanjutnya ketika verifikasi gagal kurang terstruktur.
- Pengecekan management plane (ping antar switch via VLAN 10, E8–E13) dilakukan untuk memastikan konektivitas management tidak terganggu sebelum mulai mengutak-atik konfigurasi.

**Yang perlu diperbaiki**

1. Baca output diagnosis sebelum menentukan lokasi fix: E3 sudah jelas menunjukkan fault ada di sw2/eth2, tapi fix pertama diterapkan ke sw3/eth2 (E23). Sebelum menjalankan command perubahan, tanyakan ke diri sendiri: 'output mana yang mendukung perubahan ini, di perangkat mana?'
2. Jangan menyentuh port yang tidak rusak: sw1/eth1 adalah port akses host-a yang sudah benar dikonfigurasi (E16 menunjukkan PVID/Egress Untagged VLAN 20). Perubahan E32, E102, E133, E145 semua menyentuh port ini tanpa alasan diagnostik. Aturan praktisnya: kalau belum ada bukti port itu bermasalah, jangan ubah.
3. Ketika ping masih gagal setelah fix (E100, setelah E96 yang sudah benar), lakukan diagnose ulang dulu—bukan langsung buat perubahan baru. Di sini seharusnya `bridge vlan show` di semua switch untuk melihat state keseluruhan sebelum menyentuh apapun lagi. Kamu akan melihat bahwa E23 dan E32 sudah merusak port yang sehat.
4. Pahami perbedaan port akses dan trunk di linux-bridge: port akses (ke host) harus dikonfigurasi `pvid untagged`, bukan `tagged`. Port trunk (antar switch) dikonfigurasi tanpa flag `pvid untagged`. Kesalahan ini muncul berulang di E23 (sw3/eth2 akses diberi tagged), E32 (sw1/eth1 akses diberi tagged), dan butuh beberapa rework (E133, E138, E145, E148) untuk diperbaiki.

**Pelajaran teknis**

- Di linux-bridge dengan `vlan_filtering`, port akses dikonfigurasi dengan `bridge vlan add dev <port> vid <N> pvid untagged`—flag `pvid` berarti frame untagged yang masuk diasosiasikan ke VLAN ini, dan `untagged` berarti frame keluar ke host tidak diberi tag. Port trunk cukup `bridge vlan add dev <port> vid <N>` tanpa flag tambahan (frame tetap tagged). Menambahkan `tagged` ke port akses menyebabkan frame ke host keluar dengan tag 802.1Q, yang tidak dipahami host biasa.
- Flag `PVID` dan `Egress Untagged` di output `bridge vlan show` adalah penanda penting: PVID = port akses (ingress untagged), Egress Untagged = keluar untagged. Kalau port akses kehilangan salah satu flag ini (seperti yang terjadi setelah E23 di sw3/eth2), host tidak bisa berkomunikasi meski VLAN ID-nya benar.

**Momen penting**

- `E3` sw2: `bridge -d vlan`: Diagnosis sempurna: satu command langsung menunjukkan fault. Output ini harusnya menjadi satu-satunya dasar untuk fix yang akan dilakukan.
- `E23` sw3: `bridge vlan add dev eth2 vid 20 tagged`: Titik kesalahan pertama: fix diterapkan ke sw3/eth2 (port akses host-b) padahal fault ada di sw2/eth2. Ini mengubah port akses yang sehat menjadi tagged-only, yang menjadi masalah baru.
- `E32` sw1: `bridge vlan add dev eth1 vid 20 tagged`: Perubahan kedua yang tidak perlu: menambahkan VLAN 20 tagged ke sw1/eth1 (port akses host-a yang sudah benar). Tidak ada bukti diagnostik yang mendukung ini.
- `E96` sw2: `bridge vlan add dev eth2 vid 20`: Fix yang benar akhirnya diterapkan—`bridge vlan add dev eth2 vid 20` di sw2. Ini adalah satu-satunya perubahan yang seharusnya terjadi di seluruh sesi.
- `E100` host-a: `ping 10.20.0.2`: Ping masih gagal setelah fix yang benar (E96) karena E23 dan E32 sudah merusak port akses. Ini titik kritis di mana diagnose ulang diperlukan, tapi tidak dilakukan.
- `E145` sw1: `bridge vlan add dev eth1 vid 20 pvid untagged`: Setelah beberapa rework, sw1/eth1 akhirnya dikembalikan ke pvid untagged—tapi VLAN 10 yang ditambahkan di E102 tetap ada, menyebabkan sw1/eth1 tidak bersih sebagai port akses murni (ini yang tercatat sebagai issue di verify.sh).

**Latihan berikutnya:** Di soal berikutnya, setelah menemukan fault dari output diagnostik, tulis (atau ucapkan) satu kalimat spesifik sebelum menjalankan fix: 'Saya akan mengubah X di perangkat Y karena output Z menunjukkan A.' Kalau kamu tidak bisa melengkapi kalimat itu dengan bukti dari output yang sudah terlihat, jangan jalankan command-nya dulu.

## Penilaian methodology

campuran · 45

Pemain memulai dengan diagnosis yang solid: mengecek `bridge -d vlan` di sw2 pada E3 dan menemukan fault (VLAN 20 tidak ada di eth2 sw2) dalam 31 detik. Ini adalah alur diagnosis yang tepat. Namun setelah titik itu, sesi didominasi oleh perubahan yang tidak perlu dan trial-and-error. Pemain salah menerapkan fix pertama ke sw3 (E23) alih-alih sw2, lalu menambahkan VLAN tagged ke eth1 sw1 (E32) yang merupakan port akses host-a yang sudah benar. Fix yang benar ke sw2 (E96) baru dilakukan ~34 menit setelah masalah ditemukan. Bahkan setelah fix E96, ping host-a ke host-b tetap gagal (E100), tapi pemain tidak menginvestigasi mengapa—justru menambah VLAN 10 ke eth1 sw1 (E102, port akses user), lalu mengubah flag tagged/untagged di port akses sw1 dan sw3 berulang kali (E126, E133, E138, E145, E148). Pemain tidak sadar bahwa perubahan-perubahan itu justru merusak port akses yang awalnya baik. Verifikasi dilakukan setelah setiap perubahan, tapi ketika verifikasi gagal, langkah berikutnya adalah mengubah hal lain tanpa hipotesis jelas. Akhirnya ping berhasil (E150) karena kombinasi fix sw2 + perbaikan port akses yang sempat rusak, bukan karena alur yang bersih.

- `E3` sw2: `bridge -d vlan`: Dalam 31 detik, pemain langsung `bridge -d vlan` di sw2 dan hasilnya sudah menunjukkan fault: eth2 di sw2 hanya punya VLAN 10, tidak ada VLAN 20. Ini adalah temuan yang seharusnya langsung memicu fix ke sw2/eth2.
- `E23` sw3: `bridge vlan add dev eth2 vid 20 tagged`: Fix diterapkan ke sw3/eth2 (bukan sw2/eth2 yang rusak). Bukti dari E3 sudah jelas menunjukkan sw2/eth2 yang bermasalah, tapi pemain salah sasaran perangkat.
- `E32` sw1: `bridge vlan add dev eth1 vid 20 tagged`: Menambahkan VLAN 20 tagged ke eth1 sw1—port akses host-a yang sudah benar (E16 menunjukkan eth1 sw1 sudah PVID/Egress Untagged VLAN 20). Ini perubahan tanpa dasar pada port yang sehat.
- `E96` sw2: `bridge vlan add dev eth2 vid 20`: Fix yang benar akhirnya diterapkan: `bridge vlan add dev eth2 vid 20` di sw2. Ini adalah satu-satunya perubahan yang diperlukan, tapi baru dilakukan di menit ke-34.
- `E100` host-a: `ping 10.20.0.2`: Setelah fix E96, ping masih gagal. Pemain tidak menginvestigasi kenapa (kemungkinan karena E23 dan E32 sudah merusak port akses). Seharusnya dicek dulu state semua port sebelum membuat perubahan baru.
- `E102` sw1: `bridge vlan add dev eth1 vid 10`: Tanpa bukti diagnostik apapun, pemain menambahkan VLAN 10 ke eth1 sw1 (port akses user). Ini melanggar desain (VLAN management di port user) dan tidak ada hipotesis yang mendukungnya.
- `E133` sw1: `bridge vlan add dev eth1 vid 20 untagged`: Pemain mengubah eth1 sw1 vid 20 menjadi untagged, kemudian di E145 mengubah lagi menjadi pvid untagged. Ini adalah serangkaian rework karena tidak memahami flag yang benar untuk port akses, bukan diagnosis terstruktur.
- `E148` sw3: `bridge vlan add dev eth2 vid 20 pvid untagged`: Setelah 5 rework, sw3/eth2 akhirnya di-set pvid untagged. Ping baru berhasil di E150 setelah semua port akses yang sempat dirusak diperbaiki secara tidak sengaja.

_Methodology dari 3 run: [45, 45, 45] (median 45)_
