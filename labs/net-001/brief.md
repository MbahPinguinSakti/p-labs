# Tiket #4127: host-a tidak bisa menjangkau host-b

**Pelapor:** tim aplikasi
**Prioritas:** tinggi

Setelah maintenance jaringan semalam, `host-a` (10.20.0.1) tidak bisa lagi menjangkau `host-b` (10.20.0.2). Keduanya berada di VLAN 20. Sebelum maintenance semuanya normal. Tidak ada perubahan di sisi server.

Perangkat yang bisa kamu akses: `host-a`, `host-b`, `sw1`, `sw2`, `sw3`.

| Perangkat | IP |
|---|---|
| host-a | 10.20.0.1 (VLAN 20) |
| host-b | 10.20.0.2 (VLAN 20) |
| sw1 / sw2 / sw3 | 10.10.0.11 / .12 / .13 (management, VLAN 10, interface `vlan10`) |

**Tugas:** temukan penyebabnya, perbaiki, lalu buktikan bahwa layanan sudah pulih. Jangan merusak desain jaringan yang ada (trunk membawa VLAN 10 dan 20, management switch tetap bisa saling menjangkau).

<!-- cli: bagian di bawah ini untuk terminal biasa; web UI menyembunyikannya -->
Masuk ke perangkat lewat browser: `http://localhost:7681/?arg=<node>`
atau dari terminal: `../../platform/lab-shell . <node>`

Butuh petunjuk? `../../platform/lab-hint .` membuka hint berikutnya (level 1: -3 poin, level 2: -7 poin).

Semua command di sesi ini direkam untuk penilaian.
