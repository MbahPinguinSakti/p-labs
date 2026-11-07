# Web UI

[Beranda](../README.md) › Web UI

Antarmuka P-lab: Vite + React + TypeScript. Data dan aksi berasal dari
`platform/server.py` (FastAPI). Frontend tidak menyimpan state selain hal kecil
per browser, misalnya modul Belajar yang sudah dibaca.

> [!NOTE]
> Halaman ini untuk pengembang. Untuk memasang dan memakai P-lab, lihat
> [Instalasi](../docs/instalasi.md) dan [Penggunaan](../docs/penggunaan.md).

## Menjalankan

```bash
../platform/web                 # build kalau perlu + server di http://localhost:8000
```

Mode pengembangan (hot reload), dua terminal:

```bash
python3 ../platform/server.py   # API di :8000
npm run dev                     # UI di http://localhost:5173 (proxy /api → :8000)
```

Agar "Selesai & nilai" bisa memakai AI, jalankan server dengan env provider yang
sama seperti `evaluate.py`:

```bash
LAB_LLM_PROVIDER=anthropic LAB_LLM_API_KEY_FILE=~/.config/lab/anthropic.key ../platform/web
```

Tanpa env itu, penilaian tetap bisa dijalankan tanpa AI: correctness,
efficiency, dan safety dihitung, tapi methodology dan skor akhir kosong.
Daftar provider ada di [platform/llm/README.md](../platform/llm/README.md).

## Service dan deploy dari web

`../install.sh` memasang keduanya ([panduan](../docs/instalasi.md)). Untuk
pemasangan manual:

```bash
../platform/install-service.sh        # sekali: service systemd user + ikon "P-lab" di menu
sudo ../platform/setup-sudoless.sh    # sekali: containerlab tanpa sudo, lalu logout/login
```

- **Service** `p-lab` menjalankan `platform/web` saat login dan restart sendiri
  kalau mati. Env LLM dibaca dari `~/.config/p-lab/web.env`. Log:
  `journalctl --user -u p-lab -f`.
- **Deploy dari web**: setelah containerlab sudo-less (setuid + grup
  `clab_admins`), halaman lab menampilkan **Deploy & mulai** dan **Reset lab**.
  Keduanya menjalankan `reset.sh` di background, dengan progres per tahap
  (`==> destroy/deploy/verify/inject`). Output tahap inject tidak ditampilkan
  karena bisa menyebut lokasi fault. Tanpa setup ini, UI menampilkan perintah
  `./reset.sh`.
- **Membatalkan**: `sudo ../platform/setup-sudoless.sh --undo` dan
  `../platform/install-service.sh --uninstall`.

## Struktur kode

| Path | Isi |
|---|---|
| `src/styles/` | `global.css` berisi base dan kelas bersama. `tokens.css` adalah salinan token dari folder desain yang juga dipakai website. Kalau token desain berubah, salin ulang file itu. Jangan tulis hex atau ukuran manual di komponen. |
| `src/lib/api.ts` | klien dan tipe API |
| `src/lib/hooks.ts` | `useApi`, `useLiveSession` (WebSocket), `useNow`, `useStoredSet` |
| `src/lib/catalog.ts` | lab yang direncanakan ("segera hadir"). Hapus entrinya begitu soalnya ada di `labs/`. |
| `src/lib/learn.ts` | materi halaman Belajar |
| `src/components/` | Layout (sidebar, header, akun), Cards, Topology (diagram dari `.clab.yaml` + `design.links`), Modal, Icon |
| `src/pages/` | satu file per halaman, styling dengan CSS Modules |

## Terminal

Setiap tab node adalah iframe ke ttyd (`http://<host>:7681/?arg=<node>`), yang
dijalankan server lewat `platform/lab-shell`, jadi perekamannya sama dengan CLI.
Iframe node yang pernah dibuka tetap dipasang, sehingga shell-nya tidak putus
saat pindah tab.
