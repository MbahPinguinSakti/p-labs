# P-lab

Lab troubleshooting jaringan yang berjalan di komputermu sendiri. Kamu menerima
tiket gangguan, masuk ke perangkat lewat terminal di browser, lalu mencari dan
memperbaiki masalahnya. Konsepnya mirip CTF, tapi yang dinilai bukan hanya
"berhasil atau tidak". Cara kerjamu juga dinilai: apakah kamu mendiagnosis dulu
sebelum mengubah konfigurasi, berapa banyak perubahan yang kamu buat, dan apakah
ada bagian jaringan sehat yang ikut rusak.

- **Lab sungguhan**: switch dan host berupa container ([containerlab](https://containerlab.dev)), bukan simulasi.
- **Setiap command direkam**, lalu dinilai di empat dimensi: correctness, efficiency, methodology, dan safety.
- **Evaluator AI** menilai methodology dengan mengutip command yang kamu ketik. Provider-nya bebas: Anthropic, OpenAI-compatible, atau LLM lokal.
- **Hint berjenjang**, masing-masing dengan potongan skor.
- **Bisa ditambah soal sendiri** dari template.

## Mulai cepat

Kebutuhan: Linux (Arch, Debian/Ubuntu, atau Fedora), akses sudo, dan RAM sekitar 2 GB untuk lab.

```bash
git clone <url-repo> p-lab && cd p-lab
./install.sh
```

Installer mengecek dan memasang docker, containerlab, ttyd, Python, dan Node.
Setelah itu ia membangun web UI dan memasangnya sebagai service yang jalan
otomatis saat login. Kalau sudah selesai, buka **http://localhost:8000** atau
ikon **P-lab** di menu aplikasi.

## Dokumentasi

| | |
|---|---|
| [Instalasi](docs/instalasi.md) | kebutuhan, opsi installer, deploy tanpa sudo, update, uninstall, masalah umum |
| [Penggunaan](docs/penggunaan.md) | memainkan lab di web UI, hint, penilaian, membaca hasil, mode terminal |
| [Membuat lab](docs/membuat-lab.md) | membuat soal dari template, referensi `problem.yaml`, menguji soal |
| [Arsitektur](docs/arsitektur.md) | komponen, alur data satu sesi, isi `.state/` |
| [Provider LLM](platform/llm/README.md) | memilih dan mengonfigurasi evaluator AI |

Rencana dan status pengembangan ada di [rencana.md](rencana.md). Riwayat
perubahan ada di [CHANGELOG.md](CHANGELOG.md).

## Struktur folder

```
install.sh        installer (jalankan ulang untuk update)
labs/<id>/        satu folder per soal (topologi, brief, inject, verify, problem.yaml)
platform/         server web, perekam, checkpoint, evaluator, tool CLI
platform/templates/lab/   template soal baru (dipakai platform/new-lab)
web/              antarmuka (Vite + React)
design/           token desain dan gambar referensi UI
docs/             dokumentasi
```
