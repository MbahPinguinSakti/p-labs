# Tiket #3318: Cabang C tidak bisa diakses dari kantor pusat

**Pelapor:** helpdesk
**Prioritas:** tinggi

Sejak pagi, pengguna di kantor pusat (`host-a`, 10.10.0.10) tidak bisa menjangkau server di cabang C (`host-b`, 10.30.0.10). Semalam ada pekerjaan pemeliharaan di link antar-router. Tim yang mengerjakannya bilang tidak ada perubahan routing.

Perangkat yang bisa kamu akses: `host-a`, `host-b`, `r1`, `r2`, `r3`. Router memakai **MikroTik RouterOS**.

| Segmen | Subnet | Gateway |
|---|---|---|
| LAN-A (kantor pusat) | 10.10.0.0/24 | r1 · 10.10.0.1 |
| Link r1–r2 | 10.0.12.0/30 | |
| Link r2–r3 | 10.0.23.0/30 | |
| LAN-C (cabang C) | 10.30.0.0/24 | r3 · 10.30.0.1 |

**Desain:** ketiga router saling bertukar rute lewat **OSPF area 0**, tanpa rute statis. MTU semua link 1500.

**Tugas:** temukan penyebabnya, perbaiki, lalu buktikan bahwa kantor pusat dan cabang C bisa saling menjangkau lagi. Jangan menambal dengan rute statis.

<!-- cli: bagian di bawah ini untuk terminal biasa; web UI menyembunyikannya -->
Masuk ke perangkat dari terminal: `../../platform/lab-shell . <node>`

Di router, ketik command seperti di CLI RouterOS (`/routing ospf neighbor print`, `/ip route print`). `ping` otomatis dibatasi 4 paket.

Butuh petunjuk? `../../platform/lab-hint .` membuka hint berikutnya.

Semua command di sesi ini direkam untuk penilaian.
