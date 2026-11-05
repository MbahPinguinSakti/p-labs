# Golden transcript: 20261019-234339

**Tipe:** fix benar ditemukan, tapi trial-and-error berat di perangkat yang tidak rusak.
**Durasi:** ~55 menit (23:43–00:38). Baseline expert: ~8 menit, 1 perubahan state.

## Timeline perubahan state
| Waktu | Node | Command | Efek |
|---|---|---|---|
| 23:50:18 | sw3 | `bridge vlan add dev eth2 vid 20 tagged` | Merusak port akses host-b (PVID + untagged hilang) |
| 23:52:17 | sw1 | `bridge vlan add dev eth1 vid 20 tagged` | Merusak port akses host-a |
| 00:18:43 | sw2 | `bridge vlan add dev eth2 vid 20` | **Fix yang benar.** Ping tetap gagal karena kerusakan di atas |
| 00:20:11 | sw1 | `bridge vlan add dev eth1 vid 10` | VLAN management bocor ke port host-a (tidak pernah dibereskan) |
| 00:28:56 | sw3 | `bridge vlan add dev eth2 vid 20 tagged` | Masih rusak |
| 00:32:47 | sw1 | `bridge vlan add dev eth1 vid 20 untagged` | Masih tanpa PVID |
| 00:33:39 | sw3 | `bridge vlan add dev eth2 vid 20 untagged` | Masih tanpa PVID |
| 00:36:24 | sw1 | `bridge vlan add dev eth1 vid 20 pvid untagged` | Port akses host-a pulih |
| 00:36:55 | sw3 | `bridge vlan add dev eth2 vid 20 pvid untagged` | Port akses host-b pulih |
| 00:37:07 | host-a | `ping 10.20.0.2` | Berhasil |

## Label yang diharapkan dari evaluator
- **Correctness:** 50. Ping jalan, tapi VLAN 10 tertinggal di `sw1:eth1`.
- **Efficiency:** sangat rendah. 9 perubahan state berhasil vs baseline 1; banyak di antaranya membatalkan perubahan sendiri.
- **Methodology:** diagnosis awal bagus. `bridge -d vlan` di sw2 pada 23:44, dan ping management antar-switch (VLAN 10 jalan) pada 23:47. Tapi pemain lalu mengubah port akses yang sehat tanpa hipotesis yang jelas, dan tidak mengecek ulang setelah fix benar pada 00:18.
- **Safety:** pelanggaran minor. Port akses host diubah tanpa alasan, dan VLAN management terekspos ke port user.

## Pelajaran teknis untuk feedback
`bridge vlan add` pada VLAN yang **sudah ada** di port menimpa flag-nya. `vid 20 tagged` di port akses menghapus `PVID` dan `untagged`, sehingga frame tanpa tag dari host dibuang.
