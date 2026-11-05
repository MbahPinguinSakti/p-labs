# Evaluasi net-001 · sesi 20261103-010646

**Skor akhir: 98.0**

| Dimensi | Skor | Bobot | Dasar |
|---|---|---|---|
| correctness | 100 | 30% | ping OK |
| efficiency | 100 | 20% | 1 perubahan (baseline 1), 0 rework |
| methodology | 95 | 40% | sistematis |
| safety | 100 | 10% | tidak ada pelanggaran |

## Checkpoint

- ✓ `diagnose` pada `E4` sw1: `bridge vlan show`
- ✓ `locate_fault` pada `E6` sw2: `bridge vlan show`
- ✓ `apply_fix` pada `E8` sw2: `bridge vlan add dev eth2 vid 20`
- ✓ `verify_fix` pada `E10` host-a: `ping -c 3 -W 1 10.20.0.2`
- ✓ `reasoning` (LLM): Pemain membentuk hipotesis VLAN/trunk sebelum mengubah konfigurasi. Dari E3 ia sudah menarik kesimpulan masalah layer 2 (ARP FAILED), kemudian langsung menuju switch dan memeriksa bridge vlan show secara berurutan (E4, E6, E7) untuk mencari ketidaksesuaian VLAN pada trunk port. Urutan command ini mencerminkan hipotesis yang jelas: 'ada VLAN yang hilang dari allowed list pada salah satu trunk'. Ia tidak langsung menebak fix tanpa dasar, melainkan membuktikan dulu lewat pemeriksaan VLAN table di setiap switch.

## Feedback

Sesi ini berjalan hampir sempurna. Kamu membaca sinyal ARP FAILED dengan tepat, langsung berpindah ke layer switch, memeriksa VLAN table satu per satu secara berurutan, menemukan eth2 di sw2 hanya membawa VLAN 10, lalu menerapkan satu fix yang benar tanpa menyentuh hal lain. Semua checkpoint tercapai, tidak ada rework, tidak ada pelanggaran safety. Skor akhir mencerminkan kualitas sesi ini.

**Yang sudah bagus**

- Interpretasi ARP FAILED (E3) langsung mengarahkan kamu ke layer 2—ini keputusan diagnosis yang tepat dan menghemat banyak waktu.
- Kamu memeriksa ketiga switch secara sistematis (E4, E6, E7) sebelum membuat perubahan apa pun, sehingga kamu yakin masalah ada di sw2 dan bukan di sw1 atau sw3.
- Satu fix, satu perangkat, satu perubahan (E8)—efisiensi sempurna sesuai baseline expert.
- Verifikasi dilakukan di dua level: state sw2 setelah fix (E9) dan ping end-to-end dari kedua sisi host (E10, E11).

**Yang perlu diperbaiki**

1. E5 (ping management ke sw3) tidak memberikan informasi yang membantu mempersempit lokasi fault VLAN. Management plane bisa jalan meski data plane VLAN 20 putus karena keduanya jalur yang berbeda. Untuk soal VLAN seperti ini, fokus langsung pada bridge vlan show lebih efisien.
2. Kamu memeriksa sw3 (E7) setelah menemukan anomali di sw2 (E6). Ini bagus untuk kelengkapan, tapi di sesi produksi kamu bisa langsung apply fix setelah sw2 terkonfirmasi bermasalah dan sw1 sudah bersih—sw3 bisa diverifikasi sekalian setelah fix jika diperlukan.
3. Tidak ada masalah besar di sesi ini, tapi untuk soal yang lebih kompleks ke depannya: biasakan mencatat atau menyebut hipotesis secara eksplisit sebelum berpindah perangkat, misalnya lewat komentar di terminal. Ini membantu kamu tetap fokus saat sesi lebih panjang.

**Momen penting**

- `E3` host-a: `ip neigh show dev eth1`: ARP FAILED adalah pivot paling penting di sesi ini. Output ini membuktikan host-a tidak bisa resolve MAC host-b, yang berarti masalah ada di layer 2 (VLAN/bridge), bukan IP atau routing. Kamu langsung bergerak ke switch—keputusan yang tepat.
- `E4` sw1: `bridge vlan show`: bridge vlan show di sw1 menunjukkan eth2 membawa VLAN 10+20 dengan benar. Ini membersihkan sw1 dari suspek dan mengarahkan investigasi ke sw2 atau sw3.
- `E6` sw2: `bridge vlan show`: Penemuan kritis: eth2 di sw2 hanya memiliki VLAN 10. VLAN 20 tidak ada di allowed list trunk ini—inilah root cause. Fault ditemukan di sini.
- `E8` sw2: `bridge vlan add dev eth2 vid 20`: bridge vlan add dev eth2 vid 20 di sw2 adalah fix yang tepat, minimal, dan sesuai desain. Satu perubahan menyelesaikan masalah.
- `E10` host-a: `ping -c 3 -W 1 10.20.0.2`: Ping berhasil dari host-a membuktikan VLAN 20 sudah mengalir kembali melalui seluruh jalur sw1–sw2–sw3.
- `E11` host-b: `ping -c 3 -W 1 10.20.0.1`: Ping dari host-b ke host-a memverifikasi konektivitas dua arah—sesi ditutup dengan bukti yang lengkap.

**Latihan berikutnya:** Di soal berikutnya, setelah kamu menemukan anomali pertama (seperti VLAN yang hilang di E6), tulis atau ucapkan hipotesismu secara eksplisit sebelum berpindah—misalnya 'eth2 sw2 tidak membawa VLAN 20, ini kandidat fault, cek sw3 untuk konfirmasi, lalu fix'. Kebiasaan ini akan membantumu tetap terstruktur di sesi yang lebih panjang dan kompleks.

## Penilaian methodology

sistematis · 95

Pemain menjalankan diagnosis yang sangat terarah: mulai dari verifikasi konektivitas di host-a (E1), lalu mengkonfirmasi interface dan ARP (E2–E3), kemudian bergerak ke layer switch satu per satu untuk memeriksa VLAN table (E4, E6, E7). Dari hasil bridge vlan show di sw2 (E6) ia langsung mengidentifikasi eth2 hanya membawa VLAN 10 tanpa VLAN 20, lalu menerapkan satu fix yang tepat (E8), memverifikasi perubahan di sw2 (E9), dan mengkonfirmasi konektivitas end-to-end dari kedua sisi (E10–E11). Tidak ada perubahan pada perangkat yang sehat, tidak ada rework, dan seluruh alur selesai dalam ~2,5 menit. E5 (ping ke sw3 via management) sedikit di luar jalur diagnosis utama—hasilnya tidak secara langsung membantu mempersempit lokasi fault VLAN—tapi tidak merugikan dan bisa dibaca sebagai sanity check bahwa jalur management masih hidup.

- `E1` host-a: `ping -c 2 -W 1 10.20.0.2`: Verifikasi awal masalah sesuai tiket: ping 100% loss mengkonfirmasi konektivitas putus.
- `E2` host-a: `ip -br addr show eth1`: Cek interface host-a menunjukkan eth1 UP dengan IP yang benar, menyingkirkan masalah di host-a itu sendiri.
- `E3` host-a: `ip neigh show dev eth1`: ARP FAILED membuktikan masalah ada di layer 2 (VLAN/trunk), bukan routing.
- `E4` sw1: `bridge vlan show`: bridge vlan show di sw1 menunjukkan konfigurasi access (eth1 VLAN 20) dan trunk (eth2 VLAN 10+20) sudah benar—sw1 dibebaskan dari suspek.
- `E5` sw1: `ping -c 2 -W 1 10.10.0.13`: Ping management ke sw3 berhasil; sedikit di luar alur diagnosis VLAN tapi tidak mengubah state.
- `E6` sw2: `bridge vlan show`: bridge vlan show di sw2 langsung menunjukkan eth2 hanya memiliki VLAN 10—VLAN 20 hilang. Ini titik diagnosis kritis.
- `E7` sw3: `bridge vlan show`: Verifikasi sw3 menunjukkan konfigurasi benar (eth1 VLAN 10+20, eth2 VLAN 20 access). Pemain memeriksa semua switch sebelum membuat perubahan.
- `E8` sw2: `bridge vlan add dev eth2 vid 20`: Satu perubahan tepat: bridge vlan add dev eth2 vid 20 di sw2 sesuai diagnosis. Tidak menyentuh perangkat lain.
- `E9` sw2: `bridge vlan show dev eth2`: Verifikasi langsung setelah perubahan di sw2, mengkonfirmasi eth2 sekarang membawa VLAN 10 dan 20.
- `E10` host-a: `ping -c 3 -W 1 10.20.0.2`: Ping dari host-a ke host-b berhasil—verifikasi end-to-end dari sisi asal.
- `E11` host-b: `ping -c 3 -W 1 10.20.0.1`: Ping dari host-b ke host-a berhasil—verifikasi end-to-end dari sisi tujuan. Kedua arah dikonfirmasi.

_Methodology dari 3 run: [95, 95, 95] (median 95)_
