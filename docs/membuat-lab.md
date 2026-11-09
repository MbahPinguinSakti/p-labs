# Membuat lab

[Beranda](../README.md) › Membuat lab

Satu lab adalah satu folder di `labs/<id>/`. Isinya topologi, tiket untuk
pemain, script untuk merusak dan memeriksa lab, dan `problem.yaml` yang
mengatur cara sesi direkam dan dinilai. Platform (`platform/`) tidak perlu
diubah. Web UI otomatis menemukan semua folder di `labs/` yang punya
`problem.yaml`.

## Mulai dari template

```bash
platform/new-lab net-002 --title "Port Lepas dari Bridge"
platform/lab-lint labs/net-002
labs/net-002/reset.sh                # atau tombol Deploy di web UI
```

Template (`platform/templates/lab/`) sudah berupa soal yang **langsung bisa
dimainkan**: dua host dan satu Linux bridge, dengan fault "port eth2 dilepas
dari bridge". Mainkan dulu sekali sampai selesai supaya kamu paham alurnya.
Setelah itu ubah file-filenya satu per satu menjadi skenariomu sendiri.

```
labs/net-002/
├── problem.yaml          spesifikasi soal: parameter, checkpoint, skor, hint
├── topology.clab.yaml    node dan link (containerlab)
├── brief.md              tiket yang dibaca pemain
├── inject.sh             memasang fault + menulis ground truth
├── verify.sh             memeriksa hasil → JSON correctness
├── reset.sh              satu baris: memanggil platform/reset-lab
├── autoplay/expert.yaml  skenario main otomatis (untuk golden transcript)
└── README.md             catatan soal + skenario uji manual
```

## Langkah merancang soal

Urutan ini mencegah kerja ulang:

1. **Tulis skenarionya dalam satu kalimat**: apa gejalanya, apa penyebabnya,
   dan apa perbaikan yang benar. Contoh: *"VLAN 20 hilang dari trunk sw2,
   sehingga host-a tidak bisa menjangkau host-b. Perbaikannya:
   `bridge vlan add dev eth2 vid 20`."*
2. **Tentukan jalan pintas yang salah**, yaitu cara lain yang membuat gejala
   hilang tapi merusak desain (misalnya mematikan `vlan_filtering`). Jalan pintas
   inilah yang membedakan correctness 100 dan 50, dan biasanya juga menjadi
   aturan safety.
3. **Bangun topologi yang sehat**, lalu deploy dan pastikan semuanya jalan.
4. **Tulis `verify.sh`**, lalu uji di keadaan sehat (harus 100).
5. **Tulis `inject.sh`**, lalu uji: setelah inject harus 0, dan setelah
   diperbaiki dengan benar harus 100.
6. **Tulis `problem.yaml`**: checkpoint, skor, hint.
7. **Mainkan sendiri**, lalu buat golden transcript (lihat [Menguji soal](#menguji-soal)).

## File soal

### `topology.clab.yaml`

Format [containerlab](https://containerlab.dev/manual/topo-def-file/). Tiga
aturan wajib (dicek `lab-lint`):

```yaml
name: net002                      # unik antar-lab; container jadi clab-net002-<node> (instance user: clab-net002-<user>-<node>)
topology:
  defaults:
    kind: linux
    image: nicolaka/netshoot:v0.13
    network-mode: none            # node hanya terhubung lewat link soal
    binds:
      - ../../platform/lab-rc.sh:/etc/lab/rc:ro    # hook perekaman command
      - .state/events:/var/log/lab                 # event JSONL ke host
```

- Nama file harus berakhiran `.clab.yaml`.
- Nama node hanya boleh huruf kecil, angka, dan `-`. Prefiksnya menentukan ikon
  di diagram: `sw*` jadi switch, `r<angka>` jadi router, `fw*` jadi firewall,
  dan sisanya host.
- Jangan menulis blok `mgmt`, `mgmt-ipv4`/`mgmt-ipv6`, atau `ports` (di node,
  `groups`, `kinds`, maupun `defaults`): semua instance berbagi satu docker host.
  Jaringan management per user ditambahkan otomatis saat render instance.
- Konfigurasi awal ditulis di `exec` tiap node. Isinya keadaan **sehat**; fault
  dipasang belakangan oleh `inject.sh`.

### `brief.md`

Tiket yang dibaca pemain. Baris `# ...` pertama menjadi judul tiket di web UI;
bagian setelah `:` dipakai sebagai judul. Tulis gejalanya dan **jangan
menyebut** perangkat atau port yang rusak.

Semua teks setelah penanda ini hanya muncul di mode terminal, dan disembunyikan
oleh web UI:

```markdown
<!-- cli: bagian di bawah ini untuk terminal biasa; web UI menyembunyikannya -->
```

### `inject.sh`

Kontraknya:

- Dipanggil oleh `reset-lab` **setelah** `verify.sh` menyatakan lab sehat, dan
  oleh "Mulai sesi" di web untuk sesi ulang.
- Argumen posisional bersifat opsional, dengan default sama seperti
  `parameters` di `problem.yaml`.
- **Wajib menulis `$LAB_STATE_DIR/ground_truth.json`** berisi nilai fault yang
  sebenarnya dipakai. Kuncinya harus sama dengan nama di `parameters`, karena
  nilai ini menggantikan default saat `{{parameter}}` diisi. Evaluator AI
  menerimanya secara privat; pemain tidak pernah melihatnya.
- Output-nya tidak ditampilkan ke pemain. Meski begitu, jangan mencetak lokasi
  fault, cukup `Fault injected.`.
- Tunjuk container dengan `docker exec "$(ctr <node>)" ...` (tanpa sudo), jangan
  `clab-<name>-<node>`: setiap user punya instance lab sendiri dengan nama berbeda.

### `verify.sh`

Kontraknya:

- **Baris terakhir stdout berupa JSON**:
  `{"problem": "<id>", "correctness": 0|50|100, "issues": [...]}`.
  Field tambahan boleh ada.
- `correctness`: 100 = masalah selesai **dan** desain utuh; 50 = masalah
  selesai lewat cara yang merusak desain; 0 = belum selesai.
- Exit code: 0 kalau 100, 1 kalau tidak, dan **2 kalau lab tidak bisa
  diakses** (container mati, docker tidak jalan). Exit 2 dianggap error
  lingkungan, bukan nilai 0.
- Harus **read-only**: verify dijalankan juga di tengah sesi, jadi jangan
  mengubah state.
- `issues` ditampilkan di hasil evaluasi. Tulis dalam bahasa yang dimengerti
  pemain.

Bagian yang paling banyak makan waktu adalah memeriksa bahwa desain tetap utuh.
Daftar dulu semua jalan pintas yang bisa membuat ping kembali jalan, lalu
pastikan masing-masing menghasilkan 50, bukan 100.

### `reset.sh`

Biarkan seperti di template: satu baris yang memanggil `platform/reset-lab`.
Script itu membaca `problem.yaml`, lalu menjalankan destroy, membuat `.state/`
baru, deploy, verify (harus sehat), dan inject.

### Kontrak env script soal

Lab yang sama bisa berjalan sebagai beberapa **instance** (satu per user), masing-masing
dengan nama lab containerlab dan `.state/` sendiri. Karena itu `inject.sh` dan `verify.sh`
tidak boleh menebak nama container atau lokasi state. Source helper ini di baris awal
(sebelum `cd`):

    source "$(dirname "$0")/../../platform/labenv.sh"

| Nama | Isi |
|---|---|
| `LAB_STATE_DIR` | direktori state sesi; tulis `ground_truth.json` di sini |
| `LAB_CLAB_NAME` | nama lab containerlab instance |
| `LAB_TOPO` | file topologi instance |
| `LAB_INSTANCE` | pemilik instance (`local` di install pribadi) |
| `LAB_DIR` | direktori soal (absolut) |
| `ctr <node>` | nama container node, mis. `docker exec "$(ctr sw1)" ...` |
| `ros_exec <node> <cmd>` | satu command RouterOS lewat `platform/ros.py exec` |

`reset-lab`, "Mulai sesi" di web, dan evaluator mengisi env ini. Kalau script dijalankan
manual (`./inject.sh`), nilainya otomatis mengikuti layout lama (`labs/<id>/.state`, nama
lab dari topologi). Untuk mencoba instance lain: `LAB_INSTANCE=coba ./reset.sh`.
`lab-lint` menolak script yang menulis `clab-...` atau `.state/` langsung.

Di topologi, tulis path (binds, `startup-config`) relatif terhadap direktori soal dan
pertahankan `.state/events:/var/log/lab`; untuk instance user lain P-lab merendernya ke
path absolut dan mengganti `name` menjadi `<name>-<user>`.

## Referensi `problem.yaml`

`{{nama}}` di field mana pun diganti dengan nilai `parameters`. Nilainya
diambil dari `ground_truth.json` kalau file itu ada.

### Identitas dan tampilan

| Field | Wajib | Keterangan |
|---|---|---|
| `id` | ✓ | sama dengan nama folder, misalnya `net-002` |
| `title` | ✓ | judul di kartu lab |
| `category` | | `network-engineer` atau `network-admin` |
| `difficulty` | | `beginner`, `intermediate`, atau `advanced` |
| `lab_topology` | ✓ | nama file `.clab.yaml` |
| `brief` | | default `brief.md` |
| `nos` | | aturan perubahan state di `platform/nos/<nos>.yaml`, default `linux-bridge` |
| `ui.summary` | | satu kalimat di kartu lab (jangan membocorkan fault) |
| `ui.ticket` | | nomor tiket yang tampil, misalnya `"#4127"` |
| `design.links` | | label link di diagram, dengan kunci `"a:eth1 b:eth2"` persis seperti `endpoints`. Isinya kondisi **desain**, bukan state runtime |
| `resources.mem_mb` | | perkiraan RAM satu instance lab (MB), untuk batas `capacity.mem_mb` di mode Server. Default dihitung dari topologi: ±400 MB per node `mikrotik_ros` (VM CHR 256 MB + qemu + vrnetlab), ±30 MB per node `linux`, 512 MB untuk kind lain. Isi kalau soal memakai kind lain atau VM dengan RAM besar |

### Fault dan tujuan

```yaml
parameters: {switch: sw1, port: eth2}          # nilai default fault
fault_injection:
  script: inject.sh
  description: "Port {{port}} di {{switch}} dilepas dari br0"   # untuk evaluator, privat
  expected_fix: "ip link set {{port}} master br0 di {{switch}}"  # untuk evaluator, privat
goal_state:
  check: "ping host-a ke host-b berhasil, semua port tetap di br0"
  verify_script: verify.sh
expert_baseline:
  state_changes: 1            # jumlah perubahan state yang dibuat expert (dasar efficiency)
  typical_duration_min: 5
```

### Checkpoint

Checkpoint adalah tahap proses yang terdeteksi otomatis selama sesi. Setiap
checkpoint punya `id`, `label` (teks di UI), dan `type`:

**`command_match`**: regex atas command yang diketik pemain. Command dipecah
dulu di `;`, `&&`, `||`, dan `|`, lalu setiap potongan dicocokkan sendiri.

```yaml
- id: diagnose
  label: Diagnosis awal
  type: command_match
  node: any                   # atau nama node tertentu
  pattern: '^bridge link( show.*)?\s*$'
```

Opsinya:

- `any_of: [{node, pattern}, ...]`: cocok kalau salah satu alternatif cocok.
- `after: <id>`: hanya dihitung setelah checkpoint lain tercapai.
- `expect_exit: 0`: command harus berhasil.

**`state_check`**: jalankan command read-only di node, lalu cocokkan output-nya
dengan `expect_regex`. Pengecekan diulang setiap kali ada command di node itu,
sehingga mendeteksi *hasil* perbaikan apa pun command yang dipakai.

```yaml
- id: apply_fix
  type: state_check
  node: "{{switch}}"
  command: "ip -br link show master br0"
  expect_regex: '(?m)^{{port}}@'      # (?m): ^ cocok di awal baris mana pun
```

**`llm_judge`**: dinilai evaluator AI di akhir sesi, berdasarkan `criteria`,
dan wajib disertai bukti event kalau `require_evidence: true`.

**`hidden: true`** menyembunyikan nama dan bukti checkpoint selama sesi.
Pemain hanya melihat bahwa ada "Checkpoint tersembunyi" yang tercapai. Pakai
ini untuk checkpoint yang membocorkan lokasi fault, misalnya `locate_fault`
di `node: "{{switch}}"`.

> **Jebakan regex:** pola diagnosis seperti `^bridge vlan( show)?` juga cocok
> dengan `bridge vlan add ...`, sehingga command perbaikan ikut dihitung sebagai
> diagnosis. Kunci di akhir baris (`\s*$`) atau sebut kata kerja baca secara
> eksplisit.

### Skor

```yaml
scoring:
  weights: {correctness: 0.3, efficiency: 0.2, methodology: 0.4, safety: 0.1}   # jumlah = 1
  process_gate:
    requires: [diagnose, locate_fault]   # harus tercapai...
    before: apply_fix                    # ...sebelum checkpoint ini
    applies_to: [correctness, efficiency]
  safety:
    - id: touch_healthy_port
      severity: minor                     # minor = -25, major = -50
      reason: "Mengubah port yang tidak rusak"
      any_of:
        - {node: sw1, key: '^link eth1$'}
    - id: down_or_delete_link
      severity: major
      reason: "Mematikan atau menghapus interface"
      pattern: '^ip\s+link\s+(set\s+\S+\s+.*\bdown\b|del)'
```

- Default `weights` adalah 0.4/0.2/0.3/0.1. Untuk soal troubleshooting,
  methodology sebaiknya paling besar.
- `process_gate` memberi faktor = (jumlah `requires` yang tercapai sebelum
  `before`) / (jumlah `requires`). Nilai di `applies_to` dikali faktor ini.
- Aturan **safety** hanya dicocokkan ke command yang **mengubah state**:
  - `pattern` dicocokkan ke teks command;
  - `key` dicocokkan ke objek yang diubah, menurut aturan NOS di
    `platform/nos/linux-bridge.yaml`, misalnya `vlan eth2 20`, `link eth1`, atau
    `addr eth1`;
  - `node` di level rule atau di tiap `any_of` membatasi node mana yang dihitung.
  Setiap rule dihitung sekali, walaupun dilanggar berkali-kali.

### Hint

```yaml
hints:
  - {level: 1, penalty: 3, text: "Host sudah benar. Lihat port mana saja yang ada di bridge."}
  - {level: 2, penalty: 7, text: "Bandingkan anggota br0 di {{switch}} dengan topologi."}
```

Level harus berurutan mulai dari 1. Hint pertama sebaiknya mengarahkan ke
*lapisan* yang perlu dicek, dan hint terakhir boleh menyebut perangkatnya.

## Menguji soal

### 1. Pemeriksaan statis

```bash
platform/lab-lint labs/net-002
```

Yang dicek: field wajib, `{{parameter}}` yang tidak didefinisikan, regex yang
tidak valid, script yang tidak executable, bind perekaman, node di checkpoint
yang tidak ada di topologi, jumlah bobot, `design.links` yang tidak cocok
dengan link, dan nilai parameter yang tersebut di brief (berpotensi bocor).

### 2. Skenario uji manual

Deploy (`./reset.sh`), lalu cek setiap baris tabel di README soal:

| Aksi | `verify.sh` |
|---|---|
| tidak melakukan apa-apa | 0 |
| perbaikan yang benar | 100 |
| setiap jalan pintas yang merusak desain | 50 |

Mulai ulang tanpa deploy dengan **Mulai sesi** di web, atau
`platform/autoplay.py . <skenario> --rearm`. Syaratnya lab sehat lagi.

### 3. Golden transcript

Golden transcript adalah sesi rekaman dengan label nilai yang diharapkan. Ada
dua kegunaannya: menguji bahwa evaluator menilai soal ini dengan wajar, dan
mengisi leaderboard lokal. Idealnya ada minimal tiga: **expert**, **jalan
pintas** atau **trial-and-error**, dan **nyontek** (langsung fix tanpa
diagnosis).

```bash
cd labs/net-002
../../platform/autoplay.py . autoplay/expert.yaml --capture   # main otomatis → golden/<sesi>/
../../platform/evaluate.py run golden/<sesi>                  # nilai (butuh LLM)
```

Lalu tulis `golden/<sesi>/expected.yaml` (contohnya ada di
`labs/net-001/golden/*/expected.yaml`):

```yaml
label: "expert: diagnosis sistematis, satu perubahan state"
correctness: 100
efficiency: {min: 90}
safety: 100
checkpoints_hit: [diagnose, locate_fault, apply_fix, verify_fix]
process_gate: 1.0
methodology: {min: 85}
methodology_band: [sistematis]
final: {min: 85}
max_spread: 5           # selisih methodology maksimal antar-run
```

Lalu uji:

```bash
../../platform/evaluate.py check-all . --rules-only     # bagian deterministik, tanpa LLM
../../platform/evaluate.py check-all . --repeat 3       # termasuk LLM, 3× untuk cek konsistensi
```

Sesi buatan manusia juga bisa dijadikan golden: mainkan di web, lalu jalankan
`autoplay.py . --capture-only` sebelum sesi dinilai.

### 4. Urutan skor

Soal dianggap baik kalau urutan skor golden-nya masuk akal:
**expert > jalan pintas / berantakan > nyontek**. Kalau "nyontek" mendapat skor
tinggi, periksa `process_gate`. Kalau expert terkena potongan safety, berarti
aturan safety-nya terlalu luas.

## Checklist anti-bocor

Pemain tidak boleh tahu lokasi fault dari apa pun selain hasil diagnosisnya
sendiri. Web UI tidak pernah mengirim ground truth, parameter, definisi
checkpoint, atau hint yang belum dibuka. Sisanya tanggung jawab penulis soal:

- [ ] `brief.md` dan `ui.summary` hanya menyebut gejala.
- [ ] Checkpoint yang `node`-nya perangkat rusak diberi `hidden: true`.
- [ ] `label` checkpoint yang tidak tersembunyi bersifat umum ("Terapkan perbaikan", bukan "Tambah VLAN 20 di sw2").
- [ ] `design.links` berisi desain yang seharusnya, bukan state setelah fault.
- [ ] `inject.sh` tidak mencetak detail fault.
- [ ] Hint level 1 tidak langsung menyebut perangkatnya.

## NOS selain Linux bridge

`platform/nos/<nos>.yaml` mendefinisikan command mana yang dianggap mengubah
state dan bagaimana menormalkannya menjadi `key`. File NOS bisa menggabungkan
aturan NOS lain dengan `include: [linux-bridge]`. Ini berguna kalau lab berisi
router vendor sekaligus host Linux.

Perekaman command memakai hook bash di node (`lab-rc.sh`), jadi hanya bekerja
di node yang punya bash. Untuk CLI vendor, dibutuhkan shell proxy di host,
seperti yang sudah ada untuk RouterOS.

### Lab MikroTik RouterOS

Contoh lengkapnya ada di `labs/net-002` dan `labs/net-003`. Bedanya dengan lab
Linux:

- **Topologi**: router memakai `kind: mikrotik_ros` dengan image
  `vrnetlab/mikrotik_routeros:<versi>` ([cara membangunnya](instalasi.md#lab-mikrotik-routeros)).
  Taruh `network-mode: none` di `kinds.linux`, bukan di `defaults`, karena
  router butuh jaringan management containerlab untuk SSH.
- **Interface**: `eth1` di `.clab.yaml` = `ether2` di RouterOS (`ether1` dipakai
  vrnetlab untuk management). Web UI dan `design.links` memakai nama
  `.clab.yaml`; diagram menampilkan nama RouterOS.
- **Konfigurasi sehat** ditulis sebagai script RouterOS di
  `config/<router>.rsc`, lalu dipasang saat boot lewat `startup-config:`.
- **`deploy.ready_timeout`** (detik) di `problem.yaml`: `reset-lab` menunggu
  healthcheck container dan mengulang `verify.sh` sampai sehat, karena router
  perlu boot dan protokol routing perlu konvergen. Gunakan 300–420.
- **`nos: routeros`**: aturan RouterOS ditambah aturan host Linux.
- **inject/verify** menjalankan command di router dengan
  `platform/ros.py exec . <node> '<command>'` (exit 1 kalau RouterOS menjawab
  error, exit 2 kalau SSH gagal). Untuk data yang mau diperiksa, pakai
  scripting supaya output-nya mudah diproses, misalnya
  `:put [/interface get ether3 mtu]`.
- **Checkpoint**: shell pemain (`ros.py shell`) mencatat command dalam **bentuk
  lengkap**. Kalau pemain mengetik `print` di dalam `/ip address`, yang tercatat
  adalah `/ip address print`. Jadi regex cukup mencocokkan path absolut:
  `'^/routing ospf neighbor print\b'`. `command` di `state_check` ditulis dalam
  sintaks RouterOS, dan otomatis dijalankan lewat SSH.
- **Ping dari router** selalu tercatat dengan exit 0, walaupun semua paketnya
  timeout, karena RouterOS tidak menganggapnya error. Untuk checkpoint
  verifikasi, pakai ping dari host Linux.
- **`inject.sh`** sebaiknya memastikan fault benar-benar efektif (misalnya
  host tujuan tidak lagi terjangkau), lalu gagal dengan pesan jelas kalau
  tidak. Perilaku RouterOS kadang berbeda dari RFC atau dari vendor lain.
