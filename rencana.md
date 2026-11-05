# Rencana: Labs Belajar Problem Solving (CTF-style + AI Evaluator)

## 1. Ide Utama
Website/labs yang berjalan lokal untuk belajar memecahkan masalah dunia industri dengan konsep mirip CTF dan terintegrasi AI. Domain target: Network Engineer, Network Admin, dan Cyber Security (Red Team).

**Tujuan distribusi (sejak 2026-11-05):** P-lab harus mudah dipasang dan dikembangkan orang lain, bukan hanya jalan di mesin pembuatnya.
- Pasang dengan satu perintah (`./install.sh`). Pengguna tidak perlu membuka terminal untuk bermain: server jalan sebagai service, dan lab di-deploy dari web.
- Soal baru dibuat dari template (`platform/new-lab`) dan diperiksa otomatis (`platform/lab-lint`), tanpa mengubah `platform/`.
- Dokumentasi pengguna ada di `README.md` dan `docs/` (instalasi, penggunaan, membuat lab, arsitektur).

**Scope MVP: hanya network troubleshooting di Containerlab.** Red team menyusul setelah alur evaluasi terbukti, karena butuh model isolasi keamanan yang berbeda (lihat bagian 9).

## 2. Arsitektur Konsep (3 Layer)
- **Problem Layer**: bank skenario dan generator yang menciptakan variasi masalah di lab.
- **Sandbox Layer**: VM/container tempat user bekerja, sekaligus sumber log untuk AI.
- **AI Coach Layer**: agent yang mengamati, menilai, dan memberi feedback.

**Pembagian tanggung jawab penilaian:**
- **Correctness dinilai deterministik** oleh `verify_script`, bukan oleh LLM.
- **AI menerima ground truth secara privat** (fault yang di-inject, root cause, expected fix) agar penilaian methodology dan hint relevan. AI diinstruksikan tidak membocorkan ground truth ke user di luar jenjang hint.

## 3. Alur Evaluasi AI
1. **Observasi**: rekaman terminal per node (lihat bagian 7), pcap, config diff, syslog/service status.
2. **Checkpoint detection**: tiap soal punya beberapa checkpoint (diagnosis, penyempitan, perbaikan, verifikasi). Setiap checkpoint punya matcher yang bisa dieksekusi (lihat bagian 6). Matching dijalankan **rule-based di event stream**, tanpa LLM.
3. **Decision point** (hanya di sini LLM dipanggil secara real-time):
   - user idle > N menit atau mengulang aksi yang sama -> tawarkan hint;
   - aksi destruktif terdeteksi (rule-based) -> warning;
   - `verify_script` sukses atau user menyerah -> evaluasi akhir.
4. **Evaluasi akhir**: LLM menerima transcript + ground truth + checkpoint yang tercapai + rubrik, lalu mengeluarkan JSON terstruktur: skor per dimensi, kutipan event sebagai bukti, dan narasi feedback.

## 4. Rubrik Penilaian
| Dimensi | Bobot default | Cara ukur |
|---|---|---|
| Correctness | 40% | `verify_script`: penuh (100) / parsial (50) / tidak (0) |
| Efficiency | 20% | Rumus di bawah, hanya menghitung aksi yang mengubah state |
| Methodology | 30% | LLM menilai urutan diagnosis -> hipotesis -> aksi terukur -> verifikasi, wajib mengutip event |
| Risk/Safety | 10% | Rule-based, definisi per kategori (di bawah) |

**Efficiency.** Command read-only/diagnostik (`show`, `ping`, `ip a`, `bridge vlan show`, typo, `?`) **tidak dihitung**, supaya diagnosis yang teliti tidak dihukum.
```
extra_changes = max(0, state_changes - baseline.state_changes)
efficiency    = clamp(100 - 15*extra_changes - 10*reverted_changes, 0, 100)
```
- `state_changes`: aksi yang mengubah config/state (dideteksi dari config diff).
- `reverted_changes`: perubahan yang kemudian dibatalkan sendiri oleh user (trial-and-error).

**Safety per kategori.**
- Network: aksi yang menyebabkan outage di segmen lain, shutdown interface/node yang tidak terkait, menghapus config secara massal.
- Red team: menyerang target di luar scope, merusak/menghapus data, DoS yang tidak diperlukan. Exploit di target yang sah **bukan** pelanggaran.
- `safety = clamp(100 - 25*pelanggaran_minor - 50*pelanggaran_mayor, 0, 100)`

**Skor akhir.**
```
gate        = (checkpoint proses yang tercapai SEBELUM fix) / (checkpoint proses yang diwajibkan)
raw_score   = 0.4*correctness*gate + 0.2*efficiency*gate + 0.3*methodology + 0.1*safety
final_score = max(0, raw_score - sum(hint_penalty))   # hint level 1 = 3, level 2 = 7
```

**Pelanggaran major** hanya memotong dimensi safety, tidak membatasi skor akhir (keputusan 2026-11-03). Bahayanya dijelaskan di feedback. Akibatnya, "jalan pintas" yang mendiagnosis dengan benar lalu mematikan pengaman bisa mendapat skor di atas pemain jujur yang berantakan.

**Process gate.** Hasil (correctness, efficiency) hanya dikreditkan sebanding dengan bukti diagnosis yang terjadi *sebelum* fix. Tanpa gate, pemain yang "nyontek" (langsung fix tanpa diagnosis) mendapat correctness dan efficiency sempurna, lalu mengalahkan pemain jujur yang berantakan. Urutan yang dituju: expert > jujur tapi berantakan > nyontek. Dikonfigurasi per soal di `scoring.process_gate` (`requires`, `before`, `applies_to`). Skor mentah tetap ditampilkan di laporan beserta nilai yang dikreditkan.

Bobot bisa disesuaikan per kategori (mis. red team CTF: correctness lebih dominan; network troubleshooting: methodology lebih dominan). Output ke user berupa narasi feedback, bukan angka saja.

## 5. Sumber Soal
- Forum: r/networking, r/homelab, r/sysadmin, Cisco Community, ServerFault.
- CVE dan writeup publik untuk red team (image siap pakai, mis. Vulhub).
- Post-mortem insiden publik (Cloudflare, AWS, dll).
- Proses: curator membaca thread -> ekstrak pola (root cause, gejala, diagnosis) -> tulis template terstruktur. Tahap draft bisa dibantu AI, lalu direview manusia.
- **Filter wajib: bisa direproduksi di emulasi.** Buang masalah yang bergantung pada hardware/ASIC proprietary, bug firmware tertentu, atau fisik (kabel, optik).
- Soal ditulis sebagai **parafrase pola**, bukan salinan isi thread.

## 6. Format Template Soal (contoh)
Contoh memakai Linux bridge dengan `vlan_filtering` sebagai switch L2. Alasannya: gratis, ringan, tanpa registrasi image. (FRR tidak cocok karena ia routing suite, bukan switch L2. cEOS dan Open vSwitch bisa jadi alternatif.)

```yaml
id: net-001
category: network-engineer
title: "VLAN Trunk Misconfiguration"
difficulty: intermediate
lab_topology: topo-3switch-2host.clab.yaml
nos: linux-bridge
parameters:              # diisi oleh variant
  vlan_id: 20
  faulty_switch: sw2
  trunk_port: eth2
fault_injection:
  script: inject.sh      # dipanggil: inject.sh <faulty_switch> <trunk_port> <vlan_id>
  description: "VLAN {{vlan_id}} dihapus dari allowed list trunk {{trunk_port}} di {{faulty_switch}}"
goal_state:
  check: "ping dari host-a ke host-b berhasil"
  verify_script: verify.sh
checkpoints:
  - id: diagnose
    type: command_match
    node: any
    pattern: '^(bridge (-d )?vlan( show)?|ip -d link show)'
  - id: locate_fault
    type: command_match
    node: "{{faulty_switch}}"
    pattern: '^bridge (-d )?vlan( show)?'
  - id: apply_fix
    type: state_check
    node: "{{faulty_switch}}"
    command: "bridge vlan show dev {{trunk_port}}"
    expect_regex: '\b{{vlan_id}}\b'
  - id: verify_fix
    type: command_match
    node: host-a
    pattern: '^ping '
    after: apply_fix
  - id: reasoning
    type: llm_judge
    criteria: "User membentuk hipotesis tentang VLAN/trunk sebelum mengubah config"
    require_evidence: true
expert_baseline:
  state_changes: 1
  typical_duration_min: 8
hints:
  - {level: 1, penalty: 3, text: "Coba cek status trunk di semua switch"}
  - {level: 2, penalty: 7, text: "Perhatikan VLAN yang di-allow di trunk {{faulty_switch}}"}
```

Tipe matcher checkpoint:
- `command_match`: regex atas command yang tercatat di node tertentu.
- `state_check`: menjalankan command read-only di node dan mencocokkan output.
- `llm_judge`: hanya untuk hal yang butuh interpretasi. LLM wajib mengutip event sebagai bukti.

## 7. Arsitektur Teknis
```
Frontend (dashboard, terminal in-browser, chat AI Coach)
        |                         |
Orchestrator API  <-->  AI Agent Service
        |
Lab Provisioning (Containerlab, Docker; VM untuk red team)
        |
Telemetry (terminal recorder, pcap tap, config snapshot, syslog)
```

**Capture command (gap teknis utama).** `bash_history` tidak cukup: tidak menangkap CLI perangkat (vtysh, Cli cEOS, VyOS) dan baru ditulis saat shell exit. Karena itu rekaman dilakukan di **layer terminal**: ttyd menjalankan wrapper (`script`/asciinema atau proxy PTY) per node, sehingga semua input dan output tercatat sebagai event JSONL berstempel waktu:
```json
{"ts": "...", "session": "s1", "node": "sw2", "type": "command", "data": "bridge vlan show"}
```

| Komponen | MVP (lokal, single-user) | Nanti (multi-user) |
|---|---|---|
| Network lab | Containerlab (Linux bridge / OVS, cEOS opsional) | sama |
| Cyber lab | — | Docker Compose terisolasi di dalam VM |
| Terminal browser | ttyd + xterm.js + recorder | sama |
| GUI VM | — | noVNC / Apache Guacamole |
| Backend | Satu service (FastAPI atau Go) | Orchestrator + AI service terpisah |
| Event log | File JSONL per sesi | Vector + Redis stream / NATS |
| Database | SQLite | PostgreSQL + Redis |
| AI agent | Provider-agnostic (`platform/llm/`): Claude, OpenAI-compatible, LiteLLM | sama |

**Tool AI (read-only, tanpa SSH bebas):** `get_transcript`, `get_config_snapshot`, `get_config_diff`, `get_pcap_summary`, `run_verify_script`, `get_syslog`, `get_checkpoint_status`. AI hanya observe, tidak mengubah state lab.

**Alur real-time:** command user -> recorder -> event JSONL -> checkpoint matcher (rule-based) -> decision point? -> LLM (hint/warning) -> websocket -> verify script sukses -> evaluasi final.

## 8. Skema Database (ringkas)
Tabel: `problem_templates`, `fault_variants`, `checkpoints`, `expert_baselines`, `hints`, `sessions`, `session_events`, `evaluations`, `golden_transcripts`.

Template dipisah dari variant agar satu soal punya banyak variasi (device, VLAN ID, kombinasi fault) sehingga sulit dihafal. Variant di-render dari template (Jinja) dan menjadi parameter untuk `inject.sh`, `verify.sh`, checkpoint, dan hint.

## 9. Pertimbangan Tambahan
- **Uji evaluator dengan golden transcripts.** Tiap soal punya minimal 3 transcript referensi: expert, pemula yang bingung tapi berhasil, dan "nyontek" (langsung fix tanpa diagnosis). Evaluator dianggap layak jika urutan skornya benar dan variansnya kecil saat dijalankan berulang (mis. 5x, selisih < 5 poin).
- **Isolasi lab red team.** Target vulnerable tanpa akses internet maupun host. Node containerlab umumnya berjalan privileged, jadi kategori red team dijalankan di dalam VM (libvirt/Proxmox) sebagai batas keamanan.
- Kemampuan reset lab (destroy + redeploy + re-inject).
- **Tutup jalur alternatif.** Node lab tanpa jaringan management (`network-mode: none`, akses lewat `docker exec`), supaya pemain tidak bisa "memverifikasi" lewat jalur yang bukan soal. Ditemukan di playtest net-001: ping lewat `172.20.20.x` berhasil walau jalur VLAN masih rusak.
- **Checkpoint verifikasi harus spesifik ke jalur data** (IP tujuan + node asal), bukan sekadar `^ping`.
- Hint berjenjang dengan penalti (sudah masuk ke rumus skor).
- Privasi: transcript dikirim ke provider LLM yang dipilih (pakai model lokal via Ollama kalau tidak boleh keluar mesin). Jangan ada kredensial asli di dalam lab.
- Anti-cheat dan leaderboard ditunda sampai multi-user. Untuk single-user lokal, checkpoint `llm_judge` "reasoning" sudah cukup untuk menandai fix tanpa diagnosis.

## 10. Kekurangan yang Diketahui
Belum ditangani di MVP, wajib ditutup sebelum soal diperbanyak.

### 10.1 Tidak ada topologi visual
Saat ini pemain hanya mendapat tiket teks. Diagram hanya ada sebagai komentar ASCII di file topologi, yang tidak dibaca pemain. Di dunia nyata engineer hampir selalu bekerja dengan diagram jaringan, dan tanpa itu diagnosis jadi tebak-tebakan (mis. tidak tahu `sw2:eth2` mengarah ke mana).

Arah solusi:
- **Diagram dibangkitkan dari file `.clab.yaml`** (node, link, nama interface), supaya selalu sinkron dengan lab. `containerlab graph` bisa jadi titik awal (output web/mermaid/draw.io).
- **Diagram = dokumentasi desain, bukan state runtime.** Tampilkan link fisik, interface, VLAN/subnet yang *seharusnya*. Jangan tampilkan state aktual, karena itu membocorkan fault.
- **Tingkat detail per difficulty**: beginner mendapat diagram L1+L2 lengkap, intermediate hanya fisik + subnet, advanced bisa diberi diagram yang sengaja sedikit usang (realistis di industri).
- Jangka pendek: diagram statis (mermaid/ASCII) di `brief.md`. Jangka panjang: panel diagram di web UI Fase 3, node bisa diklik untuk membuka terminalnya.

### 10.2 Terkunci di satu NOS (Linux bridge)
Pemain yang sehari-hari memakai Cisco, Juniper, Arista, dsb. justru belajar `iproute2`/`bridge`, bukan CLI yang mereka pakai di kantor. Metodologi troubleshooting memang bisa ditransfer, tapi kelancaran command tidak, dan bisa terasa tidak relevan.

Arah solusi:
- **Pisahkan konsep fault dari realisasi per NOS.** `problem.yaml` menyimpan konsep (mis. "VLAN hilang dari allowed list trunk"); tiap NOS punya `inject`, `verify`, pola checkpoint, dan teks hint sendiri:
  ```yaml
  nos_variants:
    linux-bridge: {inject: inject.sh, locate_fault: '^bridge (-d )?vlan'}
    ceos:         {inject: inject-ceos.sh, locate_fault: '^show (interfaces? )?(trunk|vlan)'}
  ```
  Pemain memilih NOS saat `reset.sh`.
- **Verifikasi tetap NOS-agnostic** sebisa mungkin: ping antar host Linux tidak bergantung vendor switch.
- **Kandidat NOS di containerlab**: Arista cEOS (CLI mirip Cisco IOS, gratis dengan registrasi; prioritas pertama), Nokia SR Linux (image bebas diunduh), SONiC. Cisco IOL/IOS-XE dan Juniper vJunos lewat vrnetlab berat dan butuh image berlisensi milik user sendiri; image vendor tidak boleh didistribusikan bersama project.
- **Perekaman perlu disesuaikan**: hook bash (`lab-rc.sh`) tidak menangkap command di CLI vendor (`Cli` cEOS, `sr_cli`). Opsinya: command accounting milik perangkat (mis. `aaa accounting commands` di cEOS, log command history SR Linux) dikirim ke events, atau parsing transcript `script` berdasarkan pola prompt per NOS.

## 11. Status Saat Ini
- Konsep, alur evaluasi, rubrik, format template, arsitektur teknis, dan skema DB sudah dirancang dan direvisi (ground truth privat, matcher checkpoint, rumus efficiency, capture terminal, stack MVP).
- Fase 0 net-001 selesai di `labs/net-001/` dan teruji di containerlab (skor 0/100/50/50 sesuai skenario).
- Fase 1 selesai di `platform/`: hook bash per node -> event JSONL, transcript mentah via `script`, `checkpoints.py` (command_match + state_check), `serve` (ttyd + watcher). ttyd teruji ujung ke ujung lewat WebSocket (2026-11-03): command dari browser tereksekusi, tercatat ke events, dan terekam ke tty.
- **Fase 2 selesai (2026-11-03).** `evaluate.py` (`run`, `check`, `check-all`), `transcript.py` (timeline E-id + hint H-id, output per command dari log tty), `scoring.py` (efficiency, safety, hint, process gate, skor akhir), `llm/` (lapisan LLM provider-agnostic, validasi schema sisi klien + 1× perbaikan; panduan di `platform/llm/README.md`), `lab-hint` (hint berjenjang yang tercatat), `autoplay.py` (golden yang bisa diulang), `prompts/evaluator-system.md`, `nos/linux-bridge.yaml`.
  - **Empat golden net-001** lolos penuh dengan Claude Sonnet 4.6 (`check-all --repeat 3`, 66/66 pengecekan, spread methodology 0):

    | Golden | Methodology | Skor akhir |
    |---|---|---|
    | expert | 95 sistematis | 98.0 |
    | jalan pintas (`vlan_filtering 0`, hint 1) | 48 campuran | 56.2 |
    | trial-and-error (playtest manusia) | 45 campuran | 38.0 |
    | nyontek | 5 tanpa_metode | 12.0 |

  - Bagian deterministik semua golden ikut diuji di unit test (`platform/tests/test_golden.py`). Alur live `evaluate.py run .` teruji pada sesi berjalan.
  - Keputusan: pelanggaran safety major tidak membatasi skor akhir, jadi jalan pintas boleh di atas trial-and-error (bagian 4).
  - Rincian dan riwayat perubahan ada di [CHANGELOG.md](CHANGELOG.md).
- Desain web UI Fase 3 ada di Figma `project_lab`: Home, Labs, Sesi Lab, Hasil Evaluasi (di bawah hierarki lab), Progress, Leaderboard, dan 3 halaman Belajar, plus frame komponen.
- **Fase 3 bagian 1 (2026-11-04): web UI jalan.** `platform/server.py` (FastAPI + WebSocket) dan `web/` (Vite + React), dibuka dengan `platform/web`:
  - semua halaman desain terisi data asli;
  - terminal ttyd per node di dalam halaman Sesi Lab, topologi yang bisa diklik;
  - checkpoint dan aktivitas live, hint berpenalti;
  - "Selesai & nilai" (dengan atau tanpa AI) dengan arsip ke `labs/<id>/sessions/`;
  - mulai sesi baru tanpa sudo kalau lab sehat.
  - Panel topologi menutup kekurangan 10.1 untuk web.
  - Leaderboard mode lokal: dibandingkan dengan golden.
  - Sisa: deteksi idle/stuck dan peringatan destruktif real-time.
- **Distribusi (2026-11-05):**
  - `install.sh`: dependensi untuk Arch, Debian/Ubuntu, dan Fedora; venv; build web; image; service systemd user; deploy sudo-less opsional; `--check`;
  - deploy/reset lab dari web (`platform/reset-lab` generik, dengan `reset.sh` per lab cukup satu baris);
  - template soal yang langsung bisa dimainkan + `new-lab` + `lab-lint`;
  - dokumentasi di `docs/`.
  - Belum diuji di distro selain Arch (CachyOS).
- **Soal MikroTik RouterOS (2026-11-06):** net-002 Subnetting Dasar dan net-003 OSPF Neighbor Stuck. Platform mendukung node `mikrotik_ros` (vrnetlab + CHR): shell proxy `ros.py` dengan rekaman command dalam bentuk lengkap, `nos/routeros.yaml`, dan `deploy.ready_timeout`. Ini menutup sebagian kekurangan 10.2 untuk RouterOS. **Belum diuji di RouterOS sungguhan** (image belum dibangun).
- Belum dikerjakan: pengumpulan soal dari forum.

## 12. Langkah Selanjutnya
1. ✅ **Fase 0, manual:** topologi containerlab `topo-3switch-2host` + `inject.sh` + `verify.sh` untuk net-001. Mainkan langsung di terminal biasa sampai skenarionya terasa realistis.
2. ✅ **Fase 1, telemetry:** ttyd + recorder -> event JSONL. Implementasi matcher `command_match` dan `state_check`.
3. ✅ **Fase 2, evaluator offline:** system prompt + tool schema. Setelah sesi selesai, LLM mengeluarkan JSON skor + bukti + narasi. Uji dengan 3 golden transcripts.
4. **Fase 3, real-time:** ✅ web UI + hint berjenjang + state live via websocket. Sisa: deteksi idle/stuck dan warning destruktif.
5. **Distribusi:** ✅ installer satu perintah, deploy dari web, template + validator soal, dokumentasi. Sisa: uji install di Debian/Ubuntu/Fedora yang bersih (VM), dan paket rilis (tag versi + catatan rilis).
6. **Fase 4, scale:** generator variant (Jinja), 5-10 soal network, lalu mulai kategori red team di dalam VM.
