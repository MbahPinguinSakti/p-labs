# Tiket #2210: Server baru di LAN-B tidak bisa dijangkau

**Pelapor:** tim aplikasi
**Prioritas:** tinggi

Server baru `host-b` (10.20.0.130) baru dipasang di LAN-B. Dari kantor pusat (`host-a`, 10.10.0.10), server itu tidak bisa dijangkau sama sekali. Tim server memastikan alamat dan gateway di `host-b` sudah sesuai dokumen desain.

Perangkat yang bisa kamu akses: `host-a`, `host-b`, `r1`, `r2`. Router memakai **MikroTik RouterOS**.

| Segmen | Subnet (desain) | Gateway |
|---|---|---|
| LAN-A (kantor pusat) | 10.10.0.0/24 | r1 · 10.10.0.1 |
| Link r1–r2 | 10.0.12.0/30 | |
| LAN-B (ruang server) | 10.20.0.0/24 | r2 · 10.20.0.1 |

**Tugas:** temukan penyebabnya, perbaiki, lalu buktikan bahwa `host-a` dan `host-b` bisa saling menjangkau. Jangan mengubah alamat server, dan jangan menambal masalah dengan rute tambahan.

<!-- cli: bagian di bawah ini untuk terminal biasa; web UI menyembunyikannya -->
Masuk ke perangkat dari terminal: `../../platform/lab-shell . <node>`

Di router, ketik command seperti di CLI RouterOS (`/ip address print`, `/ip route print`). `ping` otomatis dibatasi 4 paket.

Butuh petunjuk? `../../platform/lab-hint .` membuka hint berikutnya.

Semua command di sesi ini direkam untuk penilaian.
