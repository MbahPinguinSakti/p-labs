# Golden transcript: 20261103-012346

**Tipe:** nyontek: langsung fix tanpa diagnosis apa pun, lalu satu ping
**Sumber:** sesi otomatis (`platform/autoplay.py`, skenario `nyontek.yaml`), bukan playtest manusia. Command dan jeda berpikir ditulis tangan; rekaman, events, dan checkpoint asli dari lab.

## Alur
1. Langsung ke sw2, langsung `bridge vlan add dev eth2 vid 20`, tanpa melihat state apa pun di perangkat mana pun.
2. Satu ping dari host-a untuk memastikan berhasil.

## Label yang diharapkan dari evaluator
- **Correctness:** 100. Hasil akhirnya memang benar.
- **Efficiency:** 100 (mentah). Secara angka setara expert, karena efficiency hanya menghitung perubahan state.
- **Process gate:** 0. `diagnose` dan `locate_fault` tidak tercapai sebelum `apply_fix`, sehingga correctness dan efficiency dikreditkan 0 di skor akhir.
- **Methodology:** tanpa_metode. Tidak ada satu pun command diagnostik sebelum perubahan, dan tidak ada bukti hipotesis. Lokasi fault "diketahui" tanpa pernah diamati.
- **Safety:** 100.
- Checkpoint `diagnose` dan `locate_fault` tidak tercapai. `reasoning` tidak tercapai.
- **Tujuan golden ini:** memastikan evaluator tidak memberi skor tinggi hanya karena hasil akhir benar dan langkahnya sedikit. Skor akhir harus jelas di bawah expert.
