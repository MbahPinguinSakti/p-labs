# P-lab

Lab troubleshooting jaringan yang berjalan di komputermu sendiri. Kamu menerima
tiket gangguan, masuk ke perangkat lewat terminal di browser, lalu mencari dan
memperbaiki masalahnya. Konsepnya mirip CTF, tapi yang dinilai bukan hanya
"berhasil atau tidak". Cara kerjamu juga dinilai: apakah kamu mendiagnosis dulu
sebelum mengubah konfigurasi, berapa banyak perubahan yang kamu buat, dan apakah
ada bagian jaringan sehat yang ikut rusak.

- **Lab sungguhan**: switch, router, dan host berupa container ([containerlab](https://containerlab.dev)), bukan simulasi, termasuk router **MikroTik RouterOS** ([kebutuhan](docs/instalasi.md#lab-mikrotik-routeros)).
- **Setiap command direkam**, lalu dinilai di empat dimensi: correctness, efficiency, methodology, dan safety ([cara skor dihitung](docs/penggunaan.md#cara-skor-dihitung)).
- **Evaluator AI** menilai methodology dengan mengutip command yang kamu ketik. Provider-nya bebas: Anthropic, OpenAI-compatible, atau LLM lokal ([konfigurasi](docs/instalasi.md#evaluator-ai)).
- **Hint berjenjang**, masing-masing dengan potongan skor ([hint](docs/penggunaan.md#4-hint)).
- **Bisa ditambah soal sendiri** dari template ([membuat lab](docs/membuat-lab.md)).

## Mulai cepat

Kebutuhan: Linux (Arch, Debian/Ubuntu, atau Fedora), akses sudo, dan RAM sekitar 2 GB untuk lab ([detail kebutuhan](docs/instalasi.md#kebutuhan)).

```bash
git clone <url-repo> p-lab && cd p-lab
./install.sh
```

Installer mengecek dan memasang docker, containerlab, ttyd, Python, dan Node.
Setelah itu ia membangun web UI dan memasangnya sebagai service yang jalan
otomatis saat login. Kalau sudah selesai, buka **http://localhost:8000** atau
ikon **P-lab** di menu aplikasi.

- Apa saja yang dilakukan installer dan opsinya: [Menjalankan installer](docs/instalasi.md#menjalankan-installer)
- Supaya lab bisa di-deploy dari tombol di web: [Deploy lab tanpa sudo](docs/instalasi.md#deploy-lab-tanpa-sudo)
- Ada yang gagal: [Masalah umum](docs/instalasi.md#masalah-umum)
- Langkah berikutnya: [memainkan sesi pertamamu](docs/penggunaan.md#alur-satu-sesi)

## Dokumentasi

| | |
|---|---|
| [Instalasi](docs/instalasi.md) | kebutuhan, opsi installer, deploy tanpa sudo, update, uninstall, masalah umum |
| [Penggunaan](docs/penggunaan.md) | memainkan lab di web UI, hint, penilaian, membaca hasil, mode terminal |
| [Membuat lab](docs/membuat-lab.md) | membuat soal dari template, referensi `problem.yaml`, menguji soal |
| [Arsitektur](docs/arsitektur.md) | komponen, alur data satu sesi, isi `.state/` |
| [Provider LLM](platform/llm/README.md) | memilih dan mengonfigurasi evaluator AI |


## Struktur folder

| Path | Isi | Dokumentasi |
|---|---|---|
| `install.sh` | installer (jalankan ulang untuk update) | [Instalasi](docs/instalasi.md) |
| `labs/<id>/` | satu folder per soal: topologi, brief, inject, verify, `problem.yaml` | [Membuat lab](docs/membuat-lab.md#file-soal) |
| `platform/` | server web, perekam, checkpoint, evaluator, tool CLI | [Arsitektur](docs/arsitektur.md#modul-platform) |
| `platform/templates/lab/` | template soal baru, dipakai `platform/new-lab` | [Mulai dari template](docs/membuat-lab.md#mulai-dari-template) |
| `platform/llm/` | lapisan provider LLM | [Provider LLM](platform/llm/README.md) |
| `web/` | antarmuka (Vite + React) | [web/README.md](web/README.md) |
| `docs/` | dokumentasi | |
