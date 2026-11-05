# web/: antarmuka P-lab (Fase 3)

Vite + React + TypeScript. Data dan aksi berasal dari `platform/server.py`
(FastAPI). Tidak ada state di frontend selain hal kecil per browser, misalnya
modul Belajar yang sudah dibaca.

```bash
../platform/web                 # build kalau perlu + server di http://localhost:8000
# mode pengembangan (hot reload), dua terminal:
python3 ../platform/server.py   # API di :8000
npm run dev                     # UI di http://localhost:5173 (proxy /api → :8000)
```

Agar "Selesai & nilai" bisa memakai AI, jalankan server dengan env provider yang
sama seperti `evaluate.py`, misalnya
`LAB_LLM_PROVIDER=9router LAB_LLM_API_KEY=$(cat ~/.config/lab/9router.key) ../platform/web`.
Tanpa env itu, penilaian tetap bisa dijalankan tanpa AI: correctness, efficiency,
dan safety tetap dihitung, tapi methodology dan skor akhir kosong.

## Tanpa terminal

`../install.sh` memasang keduanya (lihat [docs/instalasi.md](../docs/instalasi.md)). Kalau mau manual:

```bash
../platform/install-service.sh        # sekali: service systemd user + ikon "P-lab" di menu
sudo ../platform/setup-sudoless.sh    # sekali: containerlab tanpa sudo, lalu logout/login
```

- **Service** `p-lab` menjalankan `platform/web` saat login, dan restart sendiri kalau
  mati. Env LLM dibaca dari `~/.config/p-lab/web.env`. File itu hanya berisi
  `LAB_LLM_API_KEY_FILE=<path>`, jadi isi key tidak pernah ditulis di sana.
  Log: `journalctl --user -u p-lab -f`.
- **Deploy dari web**: setelah containerlab sudo-less (setuid + grup `clab_admins`),
  halaman lab menampilkan **Deploy & mulai** dan **Reset lab**. Keduanya menjalankan
  `reset.sh` di background, dengan progres per tahap (`==> destroy/deploy/verify/inject`).
  Output tahap inject tidak ditampilkan karena bisa menyebut lokasi fault. Tanpa
  setup ini, UI tetap menampilkan perintah `./reset.sh`.
  Untuk membatalkan: `sudo ../platform/setup-sudoless.sh --undo` dan
  `../platform/install-service.sh --uninstall`.

## Struktur
- `src/styles/global.css`: base dan kelas bersama. Token di-import dari `../design/tokens.css` (sumber yang sama dengan website). Jangan tulis hex atau ukuran manual di komponen.
- `src/lib/api.ts`: klien dan tipe API. `hooks.ts` berisi `useApi`, `useLiveSession` (WebSocket), `useNow`, dan `useStoredSet`.
- `src/lib/catalog.ts`: lab yang direncanakan ("segera hadir"). Hapus entrinya begitu soalnya ada di `labs/`.
- `src/lib/learn.ts`: materi halaman Belajar.
- `src/components/`: Layout (sidebar, header, akun), Cards, Topology (diagram dari `.clab.yaml` + `design.links`), Modal, Icon.
- `src/pages/`: satu file per halaman, styling dengan CSS Modules.

## Terminal
Setiap tab node adalah iframe ke ttyd (`http://<host>:7681/?arg=<node>`), yang
dijalankan server lewat `platform/lab-shell`, jadi perekamannya sama dengan CLI.
Iframe node yang pernah dibuka tetap dipasang, sehingga shell-nya tidak putus
saat pindah tab.
