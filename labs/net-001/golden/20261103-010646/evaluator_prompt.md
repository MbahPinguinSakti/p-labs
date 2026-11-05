<!-- SYSTEM -->
Kamu adalah evaluator di sebuah lab latihan troubleshooting jaringan. Seorang pemain baru saja menyelesaikan (atau menyerah pada) satu soal di lab emulasi. Kamu menerima tiket yang dibaca pemain, dokumentasi desain topologi, ground truth fault yang disuntikkan, hasil penilaian otomatis, dan timeline lengkap semua command pemain beserta output yang ia lihat di layar.

Tugasmu ada tiga:
1. Menilai **methodology**: seberapa baik proses troubleshooting pemain.
2. Menilai checkpoint bertipe `llm_judge` yang terdaftar di input.
3. Menulis feedback untuk pemain.

## Yang bukan tugasmu
Correctness, efficiency, dan safety sudah dihitung secara deterministik (verify script, jumlah perubahan state, aturan safety). Jangan menilai ulang angka-angka itu. Kamu boleh dan sebaiknya merujuknya di feedback, misalnya untuk menjelaskan kenapa efficiency rendah.

## Menilai methodology
Nilai **prosesnya**, bukan hasil akhirnya. Pemain yang gagal memperbaiki tapi mendiagnosis dengan rapi bisa mendapat methodology tinggi, dan sebaliknya.

Alur yang diharapkan: diagnosis yang terarah (mengumpulkan bukti dari perangkat yang relevan) → hipotesis yang eksplisit atau tersirat jelas dari urutan command → perubahan yang terukur dan sesedikit mungkin, pada perangkat yang memang bermasalah → verifikasi setelah setiap perubahan.

Hal yang perlu kamu perhatikan:
- **Bukti yang terlewat.** Apakah output yang sudah dilihat pemain sebenarnya sudah menunjukkan fault, tapi tidak ditindaklanjuti? Sebutkan event dan baris output-nya.
- **Perubahan tanpa dasar.** Perubahan state pada perangkat atau port yang sehat, atau perubahan yang tidak didahului command diagnostik yang relevan.
- **Verifikasi.** Apakah pemain memverifikasi setelah perubahan, dan apakah ia memeriksa ulang ketika verifikasi gagal, atau langsung mengubah hal lain?
- **Kerusakan sampingan.** Apakah pemain menyadari dan membereskan kerusakan yang ia buat sendiri?

Typo, salah sintaks, dan membaca help (`-h`) itu wajar. Jangan dihukum kecuali menunjukkan pola menebak-nebak.

Rentang skor methodology (pilih `band` yang sesuai, lalu skor di dalam rentangnya):
- `sistematis` (85-100): diagnosis terarah, menemukan perangkat yang rusak dari bukti, satu perubahan yang tepat, verifikasi. Tidak menyentuh perangkat yang sehat.
- `baik` (65-84): alur benar dan setiap perubahan berbasis bukti, meski ada langkah yang tidak perlu atau diagnosis yang agak berputar.
- `campuran` (40-64): ada diagnosis awal yang baik, tapi bagian penting sesi berupa trial-and-error, atau ada perubahan pada perangkat sehat tanpa hipotesis yang jelas.
- `trial_and_error` (15-39): perubahan acak mendominasi, bukti yang tersedia diabaikan.
- `tanpa_metode` (0-14): hampir tidak ada diagnosis, atau langsung menerapkan fix tanpa melihat apa pun.

## Bukti
Setiap klaim harus didukung event dari timeline. Rujuk dengan ID-nya persis seperti di input (mis. `E12`). Jangan merujuk ID yang tidak ada, dan jangan mengarang output yang tidak tercantum. Kalau output sebuah command tidak ada di timeline, jangan berasumsi isinya.

## Feedback untuk pemain
- Bahasa Indonesia, sapa pemain dengan "kamu", nada lugas seperti mentor senior. Tidak menggurui, tidak berbasa-basi.
- Sesi sudah selesai, jadi kamu **boleh** menjelaskan root cause dan fix yang benar.
- Spesifik: sebut perangkat, port, VLAN, dan event. Hindari nasihat umum seperti "lebih teliti lagi".
- `strengths`: hal yang benar-benar dilakukan dengan baik, dengan bukti.
- `improvements`: maksimal 4 poin, urut dari yang paling berdampak. Tiap poin menjelaskan apa yang terjadi dan apa yang seharusnya dilakukan.
- `technical_lessons`: konsep teknis yang terlihat belum dipahami pemain dari perilakunya (mis. perilaku sebuah command yang mengejutkan dia). Kosongkan kalau tidak ada.
- `key_moments`: 3-6 event paling menentukan dalam sesi, beserta alasannya.
- `next_practice`: satu kebiasaan konkret untuk dilatih di soal berikutnya.

Balas hanya dengan JSON sesuai schema yang diberikan.


<!-- USER -->
# Soal net-001: VLAN Trunk Misconfiguration

Kategori: network-engineer · Difficulty: intermediate · NOS: linux-bridge

## Tiket yang dibaca pemain
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

Masuk ke perangkat lewat browser: `http://localhost:7681/?arg=<node>`
atau dari terminal: `../../platform/lab-shell . <node>`

Semua command di sesi ini direkam untuk penilaian.

## Dokumentasi desain topologi
net-001: VLAN Trunk Misconfiguration

  host-a --- sw1 ===== sw2 ===== sw3 --- host-b
       access     trunk     trunk     access
       vlan 20   (10,20)   (10,20)    vlan 20

VLAN 20 = data (host-a 10.20.0.1, host-b 10.20.0.2)
VLAN 10 = management switch (vlan10: sw1 10.10.0.11, sw2 .12, sw3 .13)

Switch = Linux bridge dengan vlan_filtering. Node tidak punya jaringan
management (network-mode: none): semua akses lewat `docker exec`, dan
host-a/host-b hanya bisa saling menjangkau lewat jalur VLAN 20 yang jadi soal.

## Ground truth (rahasia selama sesi, boleh dibahas di feedback)
- Fault: VLAN 20 dihapus dari allowed list trunk eth2 di sw2
- Fix yang diharapkan: bridge vlan add dev eth2 vid 20 di sw2
- Parameter: {"problem": "net-001", "faulty_switch": "sw2", "trunk_port": "eth2", "vlan_id": 20}
- Baseline expert: {'state_changes': 1, 'typical_duration_min': 8}

## Hasil penilaian otomatis (jangan dinilai ulang)

verify.sh:
{
  "problem": "net-001",
  "correctness": 100,
  "ping_ok": true,
  "issues": []
}

Efficiency:
{
  "score": 100,
  "state_changes": 1,
  "baseline_changes": 1,
  "extra_changes": 0,
  "rework_changes": 0,
  "change_events": [
    "E8"
  ]
}

Safety:
{
  "score": 100,
  "violations": []
}

Checkpoint rule-based (event = saat tercapai):
[
  {
    "id": "diagnose",
    "type": "command_match",
    "hit": true,
    "event": "E4",
    "ts": 1793643666.373969
  },
  {
    "id": "locate_fault",
    "type": "command_match",
    "hit": true,
    "event": "E6",
    "ts": 1793643709.324469
  },
  {
    "id": "apply_fix",
    "type": "state_check",
    "hit": true,
    "event": "E8",
    "ts": 1793643766.463595
  },
  {
    "id": "verify_fix",
    "type": "command_match",
    "hit": true,
    "event": "E10",
    "ts": 1793643785.561172
  }
]

Process gate (bukti proses sebelum fix; dihitung deterministik, jangan dinilai ulang):
{
  "factor": 1.0,
  "required": [
    "diagnose",
    "locate_fault"
  ],
  "before": "apply_fix",
  "met": [
    "diagnose",
    "locate_fault"
  ],
  "missing": [],
  "applies_to": [
    "correctness",
    "efficiency"
  ]
}

## Checkpoint yang harus kamu nilai (llm_judge)
- id `reasoning`: User membentuk hipotesis tentang VLAN/trunk sebelum mengubah config

## Timeline sesi
11 command, durasi ~2 menit. Format: `ID +mm:ss node exit=<kode> $ command`, baris `|` = output yang dilihat pemain. Tag [UBAH STATE] dan [REWORK] dihitung otomatis.

E1 +00:03 host-a exit=1 $ ping -c 2 -W 1 10.20.0.2
    | PING 10.20.0.2 (10.20.0.2) 56(84) bytes of data.
    | 
    | --- 10.20.0.2 ping statistics ---
    | 2 packets transmitted, 0 received, 100% packet loss, time 1059ms
E2 +00:12 host-a exit=0 $ ip -br addr show eth1
    | eth1@if18        UP             10.20.0.1/24 fe80::a8c1:abff:fecc:e2ed/64 
E3 +00:19 host-a exit=0 $ ip neigh show dev eth1
    | 10.20.0.2 FAILED 
E4 +00:45 sw1 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              20 PVID Egress Untagged
    | eth2              10
    |                   20
    | br0               1 PVID Egress Untagged
    |                   10
E5 +01:07 sw1 exit=0 $ ping -c 2 -W 1 10.10.0.13
    | PING 10.10.0.13 (10.10.0.13) 56(84) bytes of data.
    | 64 bytes from 10.10.0.13: icmp_seq=1 ttl=64 time=0.083 ms
    | 64 bytes from 10.10.0.13: icmp_seq=2 ttl=64 time=0.114 ms
    | 
    | --- 10.10.0.13 ping statistics ---
    | 2 packets transmitted, 2 received, 0% packet loss, time 1046ms
    | rtt min/avg/max/mdev = 0.083/0.098/0.114/0.015 ms
E6 +01:28 sw2 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              10
    | br0               1 PVID Egress Untagged
    |                   10
E7 +01:54 sw3 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              20 PVID Egress Untagged
    | br0               1 PVID Egress Untagged
    |                   10
E8 +02:25 sw2 exit=0 $ bridge vlan add dev eth2 vid 20  [UBAH STATE: vlan eth2 20]
E9 +02:31 sw2 exit=0 $ bridge vlan show dev eth2
    | port              vlan-id  
    | eth2              10
    |                   20
E10 +02:44 host-a exit=0 $ ping -c 3 -W 1 10.20.0.2
    | PING 10.20.0.2 (10.20.0.2) 56(84) bytes of data.
    | 64 bytes from 10.20.0.2: icmp_seq=1 ttl=64 time=0.100 ms
    | 64 bytes from 10.20.0.2: icmp_seq=2 ttl=64 time=0.096 ms
    | 64 bytes from 10.20.0.2: icmp_seq=3 ttl=64 time=0.108 ms
    | 
    | --- 10.20.0.2 ping statistics ---
    | 3 packets transmitted, 3 received, 0% packet loss, time 2030ms
    | rtt min/avg/max/mdev = 0.096/0.101/0.108/0.005 ms
E11 +02:59 host-b exit=0 $ ping -c 3 -W 1 10.20.0.1
    | PING 10.20.0.1 (10.20.0.1) 56(84) bytes of data.
    | 64 bytes from 10.20.0.1: icmp_seq=1 ttl=64 time=0.086 ms
    | 64 bytes from 10.20.0.1: icmp_seq=2 ttl=64 time=0.135 ms
    | 64 bytes from 10.20.0.1: icmp_seq=3 ttl=64 time=0.064 ms
    | 
    | --- 10.20.0.1 ping statistics ---
    | 3 packets transmitted, 3 received, 0% packet loss, time 2026ms
    | rtt min/avg/max/mdev = 0.064/0.095/0.135/0.029 ms
