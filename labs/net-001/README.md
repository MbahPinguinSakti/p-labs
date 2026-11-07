# net-001: VLAN Trunk Misconfiguration

[Beranda](../../README.md) › [Daftar lab](../../README.md#daftar-lab) › net-001

File untuk curator/pembuat soal. Pemain hanya membaca `brief.md`.

| File | Fungsi |
|---|---|
| `topo-3switch-2host.clab.yaml` | Topologi containerlab (Linux bridge + vlan_filtering) |
| `inject.sh` | Menyuntikkan fault dan menulis `.state/ground_truth.json` |
| `verify.sh` | Cek deterministik, output JSON `correctness` 0/50/100 |
| `reset.sh` | Destroy, deploy, cek lab sehat, lalu inject |
| `problem.yaml` | Template soal (checkpoint, hint, baseline) |
| `brief.md` | Tiket yang dibaca pemain |

## Prasyarat
- Docker Engine native (bukan Docker Desktop; containerlab perlu berjalan di network namespace host).
- containerlab: `paru -S containerlab-bin` atau `bash -c "$(curl -sL https://get.containerlab.dev)"`.

## Cara main
Jalankan `reset.sh` tanpa `sudo` (ia memanggil `sudo containerlab` sendiri), supaya `.state/` tetap milik user. User harus ada di grup `docker`.
```
./reset.sh                 # default: sw2 eth2 vlan 20
./reset.sh sw1 eth2 20     # variant lain
docker exec -it clab-net001-host-a bash
./verify.sh                # cek hasil
```

## Perekaman dan checkpoint
```
../../platform/serve .                               # ttyd + watcher, buka http://localhost:7681/?arg=sw2
../../platform/lab-shell . sw2                       # atau shell langsung di terminal
../../platform/lab-hint .                            # buka hint berikutnya (dicatat + penalti)
python3 ../../platform/checkpoints.py status .       # checkpoint sesi ini (--json untuk mesin)
```
Isi `.state/` per sesi:

| Path | Isi |
|---|---|
| `session_id` | ID sesi, dibuat `reset.sh` |
| `ground_truth.json` | Fault yang di-inject (rahasia) |
| `events/<node>.jsonl` | Satu event per command: `ts`, `node`, `data`, `exit` |
| `events/host.jsonl` | `shell_open` / `shell_close` |
| `tty/<node>-<waktu>.log` | Transcript mentah input+output (untuk evaluator LLM) |
| `checkpoints.jsonl` | Checkpoint yang tercapai beserta buktinya |

Kalau pemain masuk dengan `docker exec` langsung, command-nya tidak terekam.

## Evaluasi
```
python3 ../../platform/evaluate.py run .                 # sesi live: jalankan verify.sh, lalu nilai
python3 ../../platform/evaluate.py run . --dry-run       # tanpa LLM: skor deterministik + prompt di .state/evaluator_prompt.md
python3 ../../platform/evaluate.py check golden/20261019-234339 --rules-only   # uji bagian deterministik
python3 ../../platform/evaluate.py check golden/20261019-234339 --repeat 5     # uji penuh + konsistensi LLM
python3 ../../platform/evaluate.py check-all . --rules-only      # semua golden, deterministik (juga jalan di unit test)
python3 ../../platform/evaluate.py check-all . --repeat 3        # semua golden + LLM, plus urutan skor akhir
```
Hasil: `evaluation.json` dan `evaluation.md` di direktori sesi.

Pembagian penilaian: correctness (`verify.sh`), efficiency, safety, hint, dan checkpoint rule-based dihitung deterministik. LLM hanya menilai methodology, checkpoint `llm_judge`, dan menulis feedback, dengan bukti berupa ID event (`E12`) yang divalidasi.

Provider LLM: Claude (default), OpenAI, Gemini, OpenRouter, Groq, DeepSeek, Mistral, Together, xAI, Ollama, LM Studio, vLLM, server OpenAI-compatible apa pun, dan sisanya lewat LiteLLM. `python3 ../../platform/evaluate.py providers` menampilkan daftarnya beserta env yang belum diset; panduan lengkap ada di [platform/llm/README.md](../../platform/llm/README.md).

Konfigurasi penilaian per soal ada di `problem.yaml` bagian `scoring` (bobot, aturan safety). Klasifikasi command yang mengubah state ada di `platform/nos/<nos>.yaml`.

Golden transcript: `golden/<sesi>/` berisi salinan `.state/` sesi nyata, `notes.md` (label manusia), dan `expected.yaml` (versi mesin dari label itu).

### Golden otomatis (autoplay)
`platform/autoplay.py` memainkan skenario dari `autoplay/*.yaml` lewat `lab-shell` sungguhan. Rekaman tty, events, dan checkpoint (watcher ikut dijalankan) semuanya asli, hanya pengetiknya yang skrip. Butuh akses docker.
```
./reset.sh                                                          # lab segar + fault
../../platform/autoplay.py . autoplay/expert.yaml --capture          # main + simpan ke golden/<sesi>/
../../platform/autoplay.py . autoplay/nyontek.yaml --rearm --capture # rearm = re-inject tanpa sudo (lab harus sehat)
```
`--speed 0.5` memotong jeda berpikir menjadi setengahnya. Langkah `{hint: 1}` membuka hint lewat `lab-hint`. `--capture-only` mengarsipkan sesi yang sudah dimainkan, misalnya setelah menguji alur live `evaluate.py run .`. `notes.md` dibuat dari field `notes` di skenario, lalu `expected.yaml` ditulis tangan.

| Golden | Skenario | Yang diuji |
|---|---|---|
| `20261019-234339` | playtest manusia | trial-and-error berat, pelanggaran minor, correctness 50 |
| `20261103-010646` | `autoplay/expert.yaml` | jalur ideal, semua checkpoint berurutan |
| `20261103-012346` | `autoplay/nyontek.yaml` | process gate 0, checkpoint diagnosis tidak tercapai |
| `20261103-023553` | `autoplay/jalan-pintas.yaml` | pelanggaran major, fix yang merusak desain (correctness 50), hint |

## Web UI
```
../../platform/web        # http://localhost:8000 → Labs → VLAN Trunk Misconfiguration
```
Server menjalankan ttyd dan watcher sendiri, jadi `serve` tidak perlu. Sesi yang sudah dinilai diarsipkan ke `sessions/<sesi>/`. Kalau lab masih sehat, "Mulai sesi baru" langsung melakukan re-inject tanpa sudo. Kalau tidak sehat, pakai **Deploy & mulai** / **Reset lab** di web, yang butuh setup sekali `sudo platform/setup-sudoless.sh`; tanpa setup itu, jalankan `./reset.sh`. `reset.sh` adalah satu baris yang memanggil `platform/reset-lab`; containerlab dipanggil langsung kalau binary-nya setuid, dan lewat sudo kalau tidak. Label di web diambil dari `problem.yaml` (`ui`, `label`/`hidden` per checkpoint, dan `design.links`).

## Skenario uji manual
| Aksi pemain | Hasil `verify.sh` yang diharapkan |
|---|---|
| Tidak melakukan apa-apa | `correctness: 0` |
| `bridge vlan add dev eth2 vid 20` di sw2 | `correctness: 100` |
| `ip link set br0 type bridge vlan_filtering 0` di sw2 | `correctness: 50` (fix yang merusak desain) |
| Fix benar, tapi `bridge vlan del dev eth1 vid 10` di sw2 | `correctness: 50` (trunk + mgmt VLAN 10 putus) |
| Saat fault: `ping 10.10.0.13` dari sw1 | berhasil: trunk hidup, hanya VLAN 20 yang tidak lewat |
