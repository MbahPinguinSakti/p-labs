# net-003: OSPF Neighbor Stuck (MikroTik RouterOS)

Kantor pusat tidak bisa menjangkau cabang C. Penyebabnya: MTU `ether3` di `r2` (link ke r3) diturunkan ke 1400, sedangkan r3 tetap 1500. Paket DBD OSPF membawa MTU interface; router menolak DBD dari tetangga dengan MTU lebih besar, sehingga adjacency r2–r3 macet di ExStart/Exchange dan rute ke LAN-C tidak pernah dipelajari.

Butuh image RouterOS (sekali): `../../platform/build-routeros-image.sh`. Lihat [docs/instalasi.md](../../docs/instalasi.md#lab-mikrotik-routeros).

```bash
./reset.sh        # deploy (3 router RouterOS + konvergensi OSPF: 2-4 menit) + inject
./verify.sh       # sebelum fix: correctness 0
../../platform/lab-shell . r2
```

## Skenario uji manual
| Aksi pemain | Hasil `verify.sh` yang diharapkan |
|---|---|
| Tidak melakukan apa-apa | `correctness: 0` |
| `/interface ethernet set ether3 mtu=1500` di r2 | `correctness: 100` (tunggu neighbor Full, ±10-40 detik) |
| `/interface ethernet set ether2 mtu=1400` di r3 | `correctness: 50` (adjacency jalan, tapi MTU desain dilanggar) |
| rute statis ke 10.30.0.0/24 di r1 dan r2 + balikannya di r2 dan r3 | `correctness: 50` (rute statis) |

Status: **belum diuji di RouterOS sungguhan**. Hal pertama yang perlu dipastikan: apakah RouterOS v7 benar-benar menahan adjacency di ExStart saat MTU berbeda. `inject.sh` gagal dengan pesan jelas kalau ternyata tidak.
