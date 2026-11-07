# net-002: Subnetting Dasar (MikroTik RouterOS)

[Beranda](../../README.md) › [Daftar lab](../../README.md#daftar-lab) › net-002

Server baru `host-b` (10.20.0.130) tidak bisa dijangkau. Penyebabnya: prefix alamat LAN-B di `r2` adalah /25 (10.20.0.0–127), padahal desainnya /24. Akibatnya r2 tidak menganggap .130 terhubung langsung dan tidak punya rute ke sana.

Butuh image RouterOS (sekali): `../../platform/build-routeros-image.sh`. Lihat [docs/instalasi.md](../../docs/instalasi.md#lab-mikrotik-routeros).

```bash
./reset.sh        # deploy (RouterOS butuh 1-3 menit untuk boot) + inject
./verify.sh       # sebelum fix: correctness 0
../../platform/lab-shell . r2      # shell RouterOS (direkam)
```

## Skenario uji manual
| Aksi pemain | Hasil `verify.sh` yang diharapkan |
|---|---|
| Tidak melakukan apa-apa | `correctness: 0` |
| `/ip address set [find interface=ether3] address=10.20.0.1/24` di r2 | `correctness: 100` |
| `ip addr` host-b diganti ke 10.20.0.100/24 (gateway tetap) | `correctness: 50` (alamat server diubah) |
| `/ip route add dst-address=10.20.0.130/32 gateway=ether3` di r2 | `correctness: 50` (rute tambalan, prefix tetap /25) |

Status: **belum diuji di RouterOS sungguhan**. Uji tabel di atas setelah image dibangun.
