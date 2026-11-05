# __ID__: __TITLE__

Dibuat dari template `platform/templates/lab` (skenario contoh: port dilepas dari bridge).
Panduan mengubahnya menjadi soalmu sendiri: [docs/membuat-lab.md](../../docs/membuat-lab.md).

```bash
../../platform/lab-lint .     # cek problem.yaml + file soal
./reset.sh                    # deploy + inject (atau tombol Deploy di web UI)
./verify.sh                   # sebelum fix: correctness 0
```

## Skenario uji manual
| Aksi pemain | Hasil `verify.sh` yang diharapkan |
|---|---|
| Tidak melakukan apa-apa | `correctness: 0` |
| `ip link set eth2 master br0` di sw1 | `correctness: 100` |
