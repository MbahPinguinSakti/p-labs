# Golden transcript: 20261103-010646

**Tipe:** expert: diagnosis sistematis menyusuri jalur L2, satu perubahan state, verifikasi dua arah
**Sumber:** sesi otomatis (`platform/autoplay.py`, skenario `expert.yaml`), bukan playtest manusia. Command dan jeda berpikir ditulis tangan; rekaman, events, dan checkpoint asli dari lab.

## Alur
1. Konfirmasi gejala dari host-a: ping 10.20.0.2 gagal, IP benar, ARP ke host-b `INCOMPLETE`, jadi masalahnya di L2.
2. sw1: tabel VLAN benar (eth1 access 20, eth2 trunk 10,20).
3. Ping management VLAN 10 dari sw1 ke sw3 berhasil. Artinya link fisik dan trunk hidup, dan masalahnya spesifik VLAN 20.
4. sw2: `bridge vlan show` memperlihatkan eth2 hanya membawa VLAN 10. Root cause ditemukan.
5. sw3: dibandingkan, sisi eth1 membawa 10 dan 20. Fault terkonfirmasi di sw2:eth2.
6. Fix tunggal: `bridge vlan add dev eth2 vid 20` di sw2, lalu dicek.
7. Verifikasi dua arah: host-a → host-b dan host-b → host-a.

## Label yang diharapkan dari evaluator
- **Correctness:** 100.
- **Efficiency:** 100. 1 perubahan state = baseline, tanpa rework.
- **Methodology:** sistematis. Gejala → lapisan (ARP) → isolasi (VLAN 10 jalan, VLAN 20 tidak) → telusuri jalur → bandingkan kedua sisi trunk → fix → verifikasi.
- **Safety:** 100. Tidak menyentuh port akses atau desain VLAN lain.
