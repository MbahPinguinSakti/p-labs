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
  "correctness": 50,
  "ping_ok": true,
  "issues": [
    "sw1:eth1 (port akses) bukan access VLAN 20 murni: vlans=[10, 20] flags20=['Egress Untagged', 'PVID']"
  ]
}

Efficiency:
{
  "score": 0,
  "state_changes": 9,
  "baseline_changes": 1,
  "extra_changes": 8,
  "rework_changes": 5,
  "change_events": [
    "E23",
    "E32",
    "E96",
    "E102",
    "E126",
    "E133",
    "E138",
    "E145",
    "E148"
  ]
}

Safety:
{
  "score": 50,
  "violations": [
    {
      "id": "touch_access_port",
      "severity": "minor",
      "reason": "Mengubah port akses host yang tidak rusak (di luar jalur fault)",
      "events": [
        "E23",
        "E32",
        "E102",
        "E126",
        "E133",
        "E138",
        "E145",
        "E148"
      ]
    },
    {
      "id": "mgmt_vlan_to_user_port",
      "severity": "minor",
      "reason": "VLAN management (10) dipasang di port akses user",
      "events": [
        "E102"
      ]
    }
  ]
}

Checkpoint rule-based (event = saat tercapai):
[
  {
    "id": "diagnose",
    "type": "command_match",
    "hit": true,
    "event": "E3",
    "ts": 1792428280.760666
  },
  {
    "id": "locate_fault",
    "type": "command_match",
    "hit": true,
    "event": "E3",
    "ts": 1792428280.760666
  },
  {
    "id": "apply_fix",
    "type": "state_check",
    "hit": true,
    "event": "E96",
    "ts": 1792430323.633604
  },
  {
    "id": "verify_fix",
    "type": "command_match",
    "hit": true,
    "event": "E150",
    "ts": 1792431427.876335
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
151 command, durasi ~54 menit. Format: `ID +mm:ss node exit=<kode> $ command`, baris `|` = output yang dilihat pemain. Tag [UBAH STATE] dan [REWORK] dihitung otomatis.

E1 +00:02 host-a exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 133: eth1@if132: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default 
    |     link/ether aa:c1:ab:51:86:74 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-dbc05e4fb5aae78e
    |     inet 10.20.0.1/24 scope global eth1
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe51:8674/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E2 +00:12 sw2 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.12/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 129: eth1@if128: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff link-netnsid 2
    |     altname clab-o-8a7353bb4e7fb4cd
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 130: eth2@if131: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:2f:4f:b4 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-8532426a9c265fe9
    |     inet6 fe80::a8c1:abff:fe2f:4fb4/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E3 +00:31 sw2 exit=0 $ bridge -d vlan
    | port              vlan-id  
    | eth1              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | eth2              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | br0               1 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   10
    |                     state forwarding mcast_router 1 neigh_suppress off 
E4 +00:46 sw1 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.11/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 128: eth2@if129: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:ed:d4:96 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-86b164db1cbfedde
    |     inet6 fe80::a8c1:abff:feed:d496/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 132: eth1@if133: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff link-netnsid 0
    |     altname clab-o-cc07a502bb1208b9
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E5 +00:56 sw3 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:6b:b2:49 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe6b:b249/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:6b:b2:49 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.13/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe6b:b249/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 131: eth1@if130: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:b7:d3:52 brd ff:ff:ff:ff:ff:ff link-netnsid 2
    |     altname clab-o-bccab36ec31691f0
    |     inet6 fe80::a8c1:abff:feb7:d352/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 134: eth2@if135: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:6b:b2:49 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-2211d3cee465ae30
    |     inet6 fe80::a8c1:abff:fe6b:b249/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E6 +02:59 sw3 exit=1 $ ping 10.10.0.1
    | PING 10.10.0.1 (10.10.0.1) 56(84) bytes of data.
    | ^C
    | --- 10.10.0.1 ping statistics ---
    | 2 packets transmitted, 0 received, 100% packet loss, time 1062ms
E7 +03:02 sw3 exit=1 $ ping 10.10.0.1
    | PING 10.10.0.1 (10.10.0.1) 56(84) bytes of data.
    | ^[[A^C
    | --- 10.10.0.1 ping statistics ---
    | 2 packets transmitted, 0 received, 100% packet loss, time 1028ms
E8 +03:04 sw3 exit=0 $ ping 10.10.0.11
    | PING 10.10.0.11 (10.10.0.11) 56(84) bytes of data.
    | 64 bytes from 10.10.0.11: icmp_seq=1 ttl=64 time=0.043 ms
    | 64 bytes from 10.10.0.11: icmp_seq=2 ttl=64 time=0.078 ms
    | ^C
    | --- 10.10.0.11 ping statistics ---
    | 2 packets transmitted, 2 received, 0% packet loss, time 1006ms
    | rtt min/avg/max/mdev = 0.043/0.060/0.078/0.017 ms
E9 +03:06 sw3 exit=0 $ ping 10.10.0.12
    | PING 10.10.0.12 (10.10.0.12) 56(84) bytes of data.
    | 64 bytes from 10.10.0.12: icmp_seq=1 ttl=64 time=0.064 ms
    | ^C
    | --- 10.10.0.12 ping statistics ---
    | 1 packets transmitted, 1 received, 0% packet loss, time 0ms
    | rtt min/avg/max/mdev = 0.064/0.064/0.064/0.000 ms
E10 +03:08 sw3 exit=0 $ ping 10.10.0.13
    | PING 10.10.0.13 (10.10.0.13) 56(84) bytes of data.
    | 64 bytes from 10.10.0.13: icmp_seq=1 ttl=64 time=0.019 ms
    | ^C
    | --- 10.10.0.13 ping statistics ---
    | 1 packets transmitted, 1 received, 0% packet loss, time 0ms
    | rtt min/avg/max/mdev = 0.019/0.019/0.019/0.000 ms
E11 +03:29 sw1 exit=0 $ ping 10.10.0.12
    | PING 10.10.0.12 (10.10.0.12) 56(84) bytes of data.
    | 64 bytes from 10.10.0.12: icmp_seq=1 ttl=64 time=0.036 ms
    | 64 bytes from 10.10.0.12: icmp_seq=2 ttl=64 time=0.069 ms
    | ^C
    | --- 10.10.0.12 ping statistics ---
    | 2 packets transmitted, 2 received, 0% packet loss, time 1036ms
    | rtt min/avg/max/mdev = 0.036/0.052/0.069/0.016 ms
E12 +03:31 sw1 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.11/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 128: eth2@if129: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:ed:d4:96 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-86b164db1cbfedde
    |     inet6 fe80::a8c1:abff:feed:d496/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 132: eth1@if133: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff link-netnsid 0
    |     altname clab-o-cc07a502bb1208b9
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E13 +03:37 sw1 exit=0 $ ping 10.10.0.13
    | PING 10.10.0.13 (10.10.0.13) 56(84) bytes of data.
    | 64 bytes from 10.10.0.13: icmp_seq=1 ttl=64 time=0.057 ms
    | ^C
    | --- 10.10.0.13 ping statistics ---
    | 1 packets transmitted, 1 received, 0% packet loss, time 0ms
    | rtt min/avg/max/mdev = 0.057/0.057/0.057/0.000 ms
E14 +04:01 host-a exit=1 $ ping 10.20.0.2
    | PING 10.20.0.2 (10.20.0.2) 56(84) bytes of data.
    | ^C
    | --- 10.20.0.2 ping statistics ---
    | 4 packets transmitted, 0 received, 100% packet loss, time 3052ms
E15 +04:07 sw2 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.12/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 129: eth1@if128: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff link-netnsid 2
    |     altname clab-o-8a7353bb4e7fb4cd
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 130: eth2@if131: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:2f:4f:b4 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-8532426a9c265fe9
    |     inet6 fe80::a8c1:abff:fe2f:4fb4/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E16 +04:32 sw1 exit=0 $ bridge -d vlan
    | port              vlan-id  
    | eth1              20 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | eth2              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | br0               1 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   10
    |                     state forwarding mcast_router 1 neigh_suppress off 
E17 +04:55 sw2 exit=0 $ bridge -d vlan 
    | port              vlan-id  
    | eth1              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | eth2              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | br0               1 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   10
    |                     state forwarding mcast_router 1 neigh_suppress off 
E18 +05:08 sw3 exit=0 $ bridge -d vlan
    | port              vlan-id  
    | eth1              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | eth2              20 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | br0               1 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   10
    |                     state forwarding mcast_router 1 neigh_suppress off 
E19 +05:30 sw3 exit=255 $ bridge vlab add dev eth2 tagged
    | Object "vlab" is unknown, try "bridge help".
E20 +05:36 sw3 exit=255 $ bridge vlan add dev eth2 tagged
    | Device and VLAN ID are required arguments.
E21 +05:51 sw3 exit=255 $ bridge vlan add dev eth2 tagged vid20
    | Device and VLAN ID are required arguments.
E22 +06:05 sw3 exit=255 $ bridge vlan add dev eth2 vid20 tagged
    | Device and VLAN ID are required arguments.
E23 +06:09 sw3 exit=0 $ bridge vlan add dev eth2 vid 20 tagged  [UBAH STATE: vlan eth2 20]
E24 +06:12 sw3 exit=0 $ bridge -d vlan
    | port              vlan-id  
    | eth1              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | eth2              20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | br0               1 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   10
    |                     state forwarding mcast_router 1 neigh_suppress off 
E25 +06:37 sw2 exit=0 $ bridge -d vlan
    | port              vlan-id  
    | eth1              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | eth2              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | br0               1 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   10
    |                     state forwarding mcast_router 1 neigh_suppress off 
E26 +06:46 sw2 exit=2 $ ping 10.20.0.2
    | ping: connect: Network unreachable
E27 +06:49 sw2 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.12/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 129: eth1@if128: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff link-netnsid 2
    |     altname clab-o-8a7353bb4e7fb4cd
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 130: eth2@if131: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:2f:4f:b4 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-8532426a9c265fe9
    |     inet6 fe80::a8c1:abff:fe2f:4fb4/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E28 +07:11 host-a exit=130 $ ping 10.20.0.
    | ^C
E29 +07:15 host-a exit=0 $ ping 10.20.0.1
    | PING 10.20.0.1 (10.20.0.1) 56(84) bytes of data.
    | 64 bytes from 10.20.0.1: icmp_seq=1 ttl=64 time=0.023 ms
    | 64 bytes from 10.20.0.1: icmp_seq=2 ttl=64 time=0.067 ms
    | ^C
    | --- 10.20.0.1 ping statistics ---
    | 2 packets transmitted, 2 received, 0% packet loss, time 1019ms
    | rtt min/avg/max/mdev = 0.023/0.045/0.067/0.022 ms
E30 +07:17 host-a exit=1 $ ping 10.20.0.2
    | PING 10.20.0.2 (10.20.0.2) 56(84) bytes of data.
    | ^C
    | --- 10.20.0.2 ping statistics ---
    | 2 packets transmitted, 0 received, 100% packet loss, time 1060ms
E31 +07:40 sw1 exit=0 $ bridge -d vlan
    | port              vlan-id  
    | eth1              20 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | eth2              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | br0               1 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   10
    |                     state forwarding mcast_router 1 neigh_suppress off 
E32 +08:08 sw1 exit=0 $ bridge vlan add dev eth1 vid 20 tagged  [UBAH STATE: vlan eth1 20]
E33 +08:57 sw2 exit=0 $ bridge -d vlan
    | port              vlan-id  
    | eth1              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | eth2              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | br0               1 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   10
    |                     state forwarding mcast_router 1 neigh_suppress off 
E34 +09:31 sw2 exit=2 $ ping 10.20.0.1
    | ping: connect: Network unreachable
E35 +09:33 sw2 exit=2 $ ping 10.20.0.2
    | ping: connect: Network unreachable
E36 +09:43 sw3 exit=2 $ ping 10.20.0.1
    | ping: connect: Network unreachable
E37 +09:57 host-b exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 135: eth1@if134: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default 
    |     link/ether aa:c1:ab:40:52:5c brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-66f1b977c41626de
    |     inet 10.20.0.2/24 scope global eth1
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe40:525c/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E38 +10:03 host-b exit=1 $ ping 10.20.0.1
    | PING 10.20.0.1 (10.20.0.1) 56(84) bytes of data.
    | ^C
    | --- 10.20.0.1 ping statistics ---
    | 2 packets transmitted, 0 received, 100% packet loss, time 1002ms
E39 +10:30 host-b exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 135: eth1@if134: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default 
    |     link/ether aa:c1:ab:40:52:5c brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-66f1b977c41626de
    |     inet 10.20.0.2/24 scope global eth1
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe40:525c/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E40 +10:39 sw2 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.12/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 129: eth1@if128: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff link-netnsid 2
    |     altname clab-o-8a7353bb4e7fb4cd
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 130: eth2@if131: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:2f:4f:b4 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-8532426a9c265fe9
    |     inet6 fe80::a8c1:abff:fe2f:4fb4/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E41 +11:40 sw2 exit=0 $ bridge -d vlan 
    | port              vlan-id  
    | eth1              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | eth2              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | br0               1 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   10
    |                     state forwarding mcast_router 1 neigh_suppress off 
E42 +12:38 sw1 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.11/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 128: eth2@if129: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:ed:d4:96 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-86b164db1cbfedde
    |     inet6 fe80::a8c1:abff:feed:d496/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 132: eth1@if133: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff link-netnsid 0
    |     altname clab-o-cc07a502bb1208b9
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E43 +12:55 sw1 exit=255 $ bridge -h
    | Usage: bridge [ OPTIONS ] OBJECT { COMMAND | help }
    |        bridge [ -force ] -batch filename
    | where  OBJECT := { link | fdb | mdb | vlan | vni | monitor }
    |        OPTIONS := { -V[ersion] | -s[tatistics] | -d[etails] |
    |                     -o[neline] | -t[imestamp] | -n[etns] name |
    |                     -com[pressvlans] -c[olor] -p[retty] -j[son] }
E44 +13:04 sw1 exit=0 $ bridge -s vlan
    | port              vlan-id
    | br0               1 PVID Egress Untagged
    |                     RX: 0 bytes 0 packets
    |                     TX: 0 bytes 0 packets
    |                   10
    |                     RX: 0 bytes 0 packets
    |                     TX: 0 bytes 0 packets
    | eth2              10
    |                     RX: 0 bytes 0 packets
    |                     TX: 0 bytes 0 packets
    |                   20
    |                     RX: 0 bytes 0 packets
    |                     TX: 0 bytes 0 packets
    | eth1              20
    |                     RX: 0 bytes 0 packets
    |                     TX: 0 bytes 0 packets
E45 +13:08 sw1 exit=255 $ bridge -s vid 10
    | Object "vid" is unknown, try "bridge help".
E46 +14:16 sw1 exit=0 $ clear
E47 +15:23 sw1 exit=255 $ bridge h
    | Usage: bridge [ OPTIONS ] OBJECT { COMMAND | help }
    |        bridge [ -force ] -batch filename
    | where  OBJECT := { link | fdb | mdb | vlan | vni | monitor }
    |        OPTIONS := { -V[ersion] | -s[tatistics] | -d[etails] |
    |                     -o[neline] | -t[imestamp] | -n[etns] name |
    |                     -com[pressvlans] -c[olor] -p[retty] -j[son] }
E48 +15:26 sw1 exit=0 $ bridge -d vlan
    | port              vlan-id  
    | eth1              20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | eth2              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | br0               1 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   10
    |                     state forwarding mcast_router 1 neigh_suppress off 
E49 +15:30 sw1 exit=0 $ bridge -d link
    | 132: eth1@if133: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 master br0 state forwarding priority 32 cost 2 
    |     hairpin off guard off root_block off fastleave off learning on flood on mcast_flood on bcast_flood on mcast_router 1 mcast_to_unicast off neigh_suppress off neigh_vlan_suppress off vlan_tunnel off isolated off locked off mab off mcast_n_groups 0 mcast_max_groups 0 
    | 128: eth2@if129: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 master br0 state forwarding priority 32 cost 2 
    |     hairpin off guard off root_block off fastleave off learning on flood on mcast_flood on bcast_flood on mcast_router 1 mcast_to_unicast off neigh_suppress off neigh_vlan_suppress off vlan_tunnel off isolated off locked off mab off mcast_n_groups 0 mcast_max_groups 0 
E50 +15:48 sw1 exit=0 $ bridge -d fdb
    | 33:33:00:00:00:01 dev br0 self permanent
    | 01:00:5e:00:00:6a dev br0 self permanent
    | 33:33:00:00:00:6a dev br0 self permanent
    | 01:00:5e:00:00:01 dev br0 self permanent
    | 33:33:ff:95:e7:90 dev br0 self permanent
    | 01:80:c2:00:00:21 dev br0 self permanent
    | aa:c1:ab:95:e7:90 dev br0 vlan 10 master br0 permanent
    | aa:c1:ab:95:e7:90 dev br0 vlan 1 master br0 permanent
    | 33:33:00:00:00:01 dev vlan10 self permanent
    | 01:00:5e:00:00:01 dev vlan10 self permanent
    | 33:33:ff:95:e7:90 dev vlan10 self permanent
    | aa:c1:ab:ed:d4:96 dev eth2 vlan 20 master br0 permanent
    | aa:c1:ab:ed:d4:96 dev eth2 vlan 10 master br0 permanent
    | aa:c1:ab:ed:d4:96 dev eth2 master br0 permanent
    | 33:33:00:00:00:01 dev eth2 self permanent
    | 01:00:5e:00:00:01 dev eth2 self permanent
    | 33:33:ff:ed:d4:96 dev eth2 self permanent
    | aa:c1:ab:95:e7:90 dev eth1 vlan 20 master br0 permanent
    | aa:c1:ab:95:e7:90 dev eth1 master br0 permanent
    | 33:33:00:00:00:01 dev eth1 self permanent
    | 01:00:5e:00:00:01 dev eth1 self permanent
    | 33:33:ff:95:e7:90 dev eth1 self permanent
E51 +15:59 sw1 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.11/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 128: eth2@if129: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:ed:d4:96 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-86b164db1cbfedde
    |     inet6 fe80::a8c1:abff:feed:d496/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 132: eth1@if133: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff link-netnsid 0
    |     altname clab-o-cc07a502bb1208b9
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E52 +16:14 sw2 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.12/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 129: eth1@if128: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff link-netnsid 2
    |     altname clab-o-8a7353bb4e7fb4cd
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 130: eth2@if131: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:2f:4f:b4 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-8532426a9c265fe9
    |     inet6 fe80::a8c1:abff:fe2f:4fb4/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E53 +16:24 sw2 exit=127 $ brigde -d vlan
    | bash: brigde: command not found
E54 +16:28 sw2 exit=127 $ bridde -d vlan
    | bash: bridde: command not found
E55 +16:31 sw2 exit=0 $ bridge -d vlan
    | port              vlan-id  
    | eth1              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   20
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | eth2              10
    |                     state forwarding mcast_router 1 neigh_suppress off 
    | br0               1 PVID Egress Untagged
    |                     state forwarding mcast_router 1 neigh_suppress off 
    |                   10
    |                     state forwarding mcast_router 1 neigh_suppress off 
E56 +16:57 sw2 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.12/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 129: eth1@if128: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff link-netnsid 2
    |     altname clab-o-8a7353bb4e7fb4cd
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 130: eth2@if131: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:2f:4f:b4 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-8532426a9c265fe9
    |     inet6 fe80::a8c1:abff:fe2f:4fb4/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E57 +17:36 sw2 exit=255 $ bridge add dev vlan10 vid 10 tagged
    | Object "add" is unknown, try "bridge help".
E58 +17:41 sw2 exit=255 $ bridge vlan add dev vlan10 vid 10 tagged
    | RTNETLINK answers: Not supported
E59 +23:06 sw2 exit=0 $ clear
E60 +23:07 sw2 exit=0 $ ip -br addr
    | lo               UNKNOWN        127.0.0.1/8 ::1/128 
    | br0              UP             fe80::a8c1:abff:fe0c:1ed0/64 
    | vlan10@br0       UP             10.10.0.12/24 fe80::a8c1:abff:fe0c:1ed0/64 
    | eth1@if128       UP             fe80::a8c1:abff:fe0c:1ed0/64 
    | eth2@if131       UP             fe80::a8c1:abff:fe2f:4fb4/64 
E61 +23:39 sw2 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              10
    | br0               1 PVID Egress Untagged
    |                   10
E62 +24:22 sw2 exit=0 $ bridge fdb show
    | 33:33:00:00:00:01 dev br0 self permanent
    | 01:00:5e:00:00:6a dev br0 self permanent
    | 33:33:00:00:00:6a dev br0 self permanent
    | 01:00:5e:00:00:01 dev br0 self permanent
    | 33:33:ff:0c:1e:d0 dev br0 self permanent
    | 01:80:c2:00:00:21 dev br0 self permanent
    | aa:c1:ab:0c:1e:d0 dev br0 vlan 1 master br0 permanent
    | 33:33:00:00:00:01 dev vlan10 self permanent
    | 01:00:5e:00:00:01 dev vlan10 self permanent
    | 33:33:ff:0c:1e:d0 dev vlan10 self permanent
    | aa:c1:ab:0c:1e:d0 dev eth1 vlan 20 master br0 permanent
    | aa:c1:ab:0c:1e:d0 dev eth1 vlan 10 master br0 permanent
    | aa:c1:ab:0c:1e:d0 dev eth1 master br0 permanent
    | 33:33:00:00:00:01 dev eth1 self permanent
    | 01:00:5e:00:00:01 dev eth1 self permanent
    | 33:33:ff:0c:1e:d0 dev eth1 self permanent
    | aa:c1:ab:2f:4f:b4 dev eth2 vlan 10 master br0 permanent
    | aa:c1:ab:2f:4f:b4 dev eth2 master br0 permanent
    | 33:33:00:00:00:01 dev eth2 self permanent
    | 01:00:5e:00:00:01 dev eth2 self permanent
    | 33:33:ff:2f:4f:b4 dev eth2 self permanent
E63 +24:38 sw2 exit=0 $ bridge -s vlan show
    | port              vlan-id
    | br0               1 PVID Egress Untagged
    |                     RX: 0 bytes 0 packets
    |                     TX: 0 bytes 0 packets
    |                   10
    |                     RX: 0 bytes 0 packets
    |                     TX: 0 bytes 0 packets
    | eth1              10
    |                     RX: 0 bytes 0 packets
    |                     TX: 0 bytes 0 packets
    |                   20
    |                     RX: 0 bytes 0 packets
    |                     TX: 0 bytes 0 packets
    | eth2              10
    |                     RX: 0 bytes 0 packets
    |                     TX: 0 bytes 0 packets
E64 +25:04 sw2 exit=0 $ clear
E65 +25:12 sw2 exit=1 $ ip br link
    | Object "br" is unknown, try "ip help".
E66 +25:29 sw2 exit=0 $ ip -br link
    | lo               UNKNOWN        00:00:00:00:00:00 <LOOPBACK,UP,LOWER_UP> 
    | br0              UP             aa:c1:ab:0c:1e:d0 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | vlan10@br0       UP             aa:c1:ab:0c:1e:d0 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | eth1@if128       UP             aa:c1:ab:0c:1e:d0 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | eth2@if131       UP             aa:c1:ab:2f:4f:b4 <BROADCAST,MULTICAST,UP,LOWER_UP> 
E67 +25:39 sw2 exit=0 $ ip -br addr
    | lo               UNKNOWN        127.0.0.1/8 ::1/128 
    | br0              UP             fe80::a8c1:abff:fe0c:1ed0/64 
    | vlan10@br0       UP             10.10.0.12/24 fe80::a8c1:abff:fe0c:1ed0/64 
    | eth1@if128       UP             fe80::a8c1:abff:fe0c:1ed0/64 
    | eth2@if131       UP             fe80::a8c1:abff:fe2f:4fb4/64 
E68 +25:50 sw2 exit=127 $ brigde link
    | bash: brigde: command not found
E69 +25:54 sw2 exit=0 $ bridge link
    | 129: eth1@if128: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 master br0 state forwarding priority 32 cost 2 
    | 130: eth2@if131: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 master br0 state forwarding priority 32 cost 2 
E70 +26:09 sw2 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              10
    | br0               1 PVID Egress Untagged
    |                   10
E71 +27:11 sw3 exit=0 $ ip -br link
    | lo               UNKNOWN        00:00:00:00:00:00 <LOOPBACK,UP,LOWER_UP> 
    | br0              UP             aa:c1:ab:6b:b2:49 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | vlan10@br0       UP             aa:c1:ab:6b:b2:49 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | eth1@if130       UP             aa:c1:ab:b7:d3:52 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | eth2@if135       UP             aa:c1:ab:6b:b2:49 <BROADCAST,MULTICAST,UP,LOWER_UP> 
E72 +27:18 sw3 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              20
    | br0               1 PVID Egress Untagged
    |                   10
E73 +27:35 sw1 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              20
    | eth2              10
    |                   20
    | br0               1 PVID Egress Untagged
    |                   10
E74 +28:22 sw1 exit=0 $ ip -br link show eth1
    | eth1@if133       UP             aa:c1:ab:95:e7:90 <BROADCAST,MULTICAST,UP,LOWER_UP> 
E75 +28:34 sw1 exit=0 $ ip -d link show eth1
    | 132: eth1@if133: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP mode DEFAULT group default 
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff link-netnsid 0 promiscuity 1 allmulti 1 minmtu 68 maxmtu 65535 
    |     veth 
    |     bridge_slave state forwarding priority 32 cost 2 hairpin off guard off root_block off fastleave off learning on flood on port_id 0x8001 port_no 0x1 designated_port 32769 designated_cost 0 designated_bridge 8000.AA:C1:AB:95:E7:90 designated_root 8000.AA:C1:AB:95:E7:90 hold_timer    0.00 message_age_timer    0.00 forward_delay_timer    0.00 topology_change_ack 0 config_pending 0 proxy_arp off proxy_arp_wifi off mcast_router 1 mcast_fast_leave off mcast_flood on bcast_flood on mcast_to_unicast off neigh_suppress off neigh_vlan_suppress off group_fwd_mask 0 group_fwd_mask_str 0x0 vlan_tunnel off isolated off locked off mab off addrgenmode eui64 numtxqueues 16 numrxqueues 16 gso_max_size 65536 gso_max_segs 65535 tso_max_size 524280 tso_max_segs 65535 gro_max_size 65536 gso_ipv4_max_size 65536 gro_ipv4_max_size 65536 
    |     altname clab-o-cc07a502bb1208b9
E76 +28:46 sw1 exit=0 $ ip -d link show eth2
    | 128: eth2@if129: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP mode DEFAULT group default 
    |     link/ether aa:c1:ab:ed:d4:96 brd ff:ff:ff:ff:ff:ff link-netnsid 1 promiscuity 1 allmulti 1 minmtu 68 maxmtu 65535 
    |     veth 
    |     bridge_slave state forwarding priority 32 cost 2 hairpin off guard off root_block off fastleave off learning on flood on port_id 0x8002 port_no 0x2 designated_port 32770 designated_cost 0 designated_bridge 8000.AA:C1:AB:95:E7:90 designated_root 8000.AA:C1:AB:95:E7:90 hold_timer    0.00 message_age_timer    0.00 forward_delay_timer    0.00 topology_change_ack 0 config_pending 0 proxy_arp off proxy_arp_wifi off mcast_router 1 mcast_fast_leave off mcast_flood on bcast_flood on mcast_to_unicast off neigh_suppress off neigh_vlan_suppress off group_fwd_mask 0 group_fwd_mask_str 0x0 vlan_tunnel off isolated off locked off mab off addrgenmode eui64 numtxqueues 16 numrxqueues 16 gso_max_size 65536 gso_max_segs 65535 tso_max_size 524280 tso_max_segs 65535 gro_max_size 65536 gso_ipv4_max_size 65536 gro_ipv4_max_size 65536 
    |     altname clab-o-86b164db1cbfedde
E77 +28:52 sw1 exit=0 $ ip -d link show br0
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP mode DEFAULT group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff promiscuity 0 allmulti 0 minmtu 68 maxmtu 65535 
    |     bridge forward_delay 1500 hello_time 200 max_age 2000 ageing_time 30000 stp_state 0 priority 32768 vlan_filtering 1 vlan_protocol 802.1Q bridge_id 8000.AA:C1:AB:95:E7:90 designated_root 8000.AA:C1:AB:95:E7:90 root_port 0 root_path_cost 0 topology_change 0 topology_change_detected 0 hello_timer    0.00 tcn_timer    0.00 topology_change_timer    0.00 gc_timer   17.85 fdb_n_learned 0 fdb_max_learned 0 vlan_default_pvid 1 vlan_stats_enabled 0 vlan_stats_per_port 0 group_fwd_mask 0 group_address 01:80:c2:00:00:00 mcast_snooping 1 no_linklocal_learn 0 mcast_vlan_snooping 0 mcast_router 1 mcast_query_use_ifaddr 0 mcast_querier 0 mcast_hash_elasticity 16 mcast_hash_max 4096 mcast_last_member_count 2 mcast_startup_query_count 2 mcast_last_member_interval 100 mcast_membership_interval 26000 mcast_querier_interval 25500 mcast_query_interval 12500 mcast_query_response_interval 1000 mcast_startup_query_interval 3125 mcast_stats_enabled 0 mcast_igmp_version 2 mcast_mld_version 1 nf_call_iptables 0 nf_call_ip6tables 0 nf_call_arptables 0 addrgenmode eui64 numtxqueues 1 numrxqueues 1 gso_max_size 65536 gso_max_segs 65535 tso_max_size 524280 tso_max_segs 65535 gro_max_size 65536 gso_ipv4_max_size 65536 gro_ipv4_max_size 65536 
E78 +28:55 sw1 exit=0 $ clear
E79 +29:00 sw1 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.11/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 128: eth2@if129: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:ed:d4:96 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-86b164db1cbfedde
    |     inet6 fe80::a8c1:abff:feed:d496/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 132: eth1@if133: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff link-netnsid 0
    |     altname clab-o-cc07a502bb1208b9
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E80 +29:07 sw1 exit=0 $ ip -br link
    | lo               UNKNOWN        00:00:00:00:00:00 <LOOPBACK,UP,LOWER_UP> 
    | br0              UP             aa:c1:ab:95:e7:90 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | vlan10@br0       UP             aa:c1:ab:95:e7:90 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | eth2@if129       UP             aa:c1:ab:ed:d4:96 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | eth1@if133       UP             aa:c1:ab:95:e7:90 <BROADCAST,MULTICAST,UP,LOWER_UP> 
E81 +29:32 sw2 exit=0 $ ip -br link
    | lo               UNKNOWN        00:00:00:00:00:00 <LOOPBACK,UP,LOWER_UP> 
    | br0              UP             aa:c1:ab:0c:1e:d0 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | vlan10@br0       UP             aa:c1:ab:0c:1e:d0 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | eth1@if128       UP             aa:c1:ab:0c:1e:d0 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | eth2@if131       UP             aa:c1:ab:2f:4f:b4 <BROADCAST,MULTICAST,UP,LOWER_UP> 
E82 +29:55 sw2 exit=0 $ bridge fdb show br br0
    | 33:33:00:00:00:01 dev br0 self permanent
    | 01:00:5e:00:00:6a dev br0 self permanent
    | 33:33:00:00:00:6a dev br0 self permanent
    | 01:00:5e:00:00:01 dev br0 self permanent
    | 33:33:ff:0c:1e:d0 dev br0 self permanent
    | 01:80:c2:00:00:21 dev br0 self permanent
    | aa:c1:ab:0c:1e:d0 dev br0 vlan 1 master br0 permanent
    | aa:c1:ab:0c:1e:d0 dev eth1 vlan 20 master br0 permanent
    | aa:c1:ab:0c:1e:d0 dev eth1 vlan 10 master br0 permanent
    | aa:c1:ab:0c:1e:d0 dev eth1 master br0 permanent
    | 33:33:00:00:00:01 dev eth1 self permanent
    | 01:00:5e:00:00:01 dev eth1 self permanent
    | 33:33:ff:0c:1e:d0 dev eth1 self permanent
    | aa:c1:ab:2f:4f:b4 dev eth2 vlan 10 master br0 permanent
    | aa:c1:ab:2f:4f:b4 dev eth2 master br0 permanent
    | 33:33:00:00:00:01 dev eth2 self permanent
    | 01:00:5e:00:00:01 dev eth2 self permanent
    | 33:33:ff:2f:4f:b4 dev eth2 self permanent
E83 +30:37 sw3 exit=0 $ bridge fdb show br br0
    | 33:33:00:00:00:01 dev br0 self permanent
    | 01:00:5e:00:00:6a dev br0 self permanent
    | 33:33:00:00:00:6a dev br0 self permanent
    | 01:00:5e:00:00:01 dev br0 self permanent
    | 33:33:ff:6b:b2:49 dev br0 self permanent
    | 01:80:c2:00:00:21 dev br0 self permanent
    | aa:c1:ab:6b:b2:49 dev br0 vlan 10 master br0 permanent
    | aa:c1:ab:6b:b2:49 dev br0 vlan 1 master br0 permanent
    | aa:c1:ab:95:e7:90 dev eth1 vlan 10 master br0 
    | aa:c1:ab:b7:d3:52 dev eth1 vlan 20 master br0 permanent
    | aa:c1:ab:b7:d3:52 dev eth1 vlan 10 master br0 permanent
    | aa:c1:ab:b7:d3:52 dev eth1 master br0 permanent
    | 33:33:00:00:00:01 dev eth1 self permanent
    | 01:00:5e:00:00:01 dev eth1 self permanent
    | 33:33:ff:b7:d3:52 dev eth1 self permanent
    | aa:c1:ab:6b:b2:49 dev eth2 vlan 20 master br0 permanent
    | aa:c1:ab:6b:b2:49 dev eth2 master br0 permanent
    | 33:33:00:00:00:01 dev eth2 self permanent
    | 01:00:5e:00:00:01 dev eth2 self permanent
    | 33:33:ff:6b:b2:49 dev eth2 self permanent
E84 +30:43 sw3 exit=0 $ bridge fdb show br eth1
E85 +30:45 sw3 exit=0 $ bridge fdb show br eth2
E86 +30:48 sw3 exit=0 $ bridge fdb show br br0
    | 33:33:00:00:00:01 dev br0 self permanent
    | 01:00:5e:00:00:6a dev br0 self permanent
    | 33:33:00:00:00:6a dev br0 self permanent
    | 01:00:5e:00:00:01 dev br0 self permanent
    | 33:33:ff:6b:b2:49 dev br0 self permanent
    | 01:80:c2:00:00:21 dev br0 self permanent
    | aa:c1:ab:6b:b2:49 dev br0 vlan 10 master br0 permanent
    | aa:c1:ab:6b:b2:49 dev br0 vlan 1 master br0 permanent
    | aa:c1:ab:95:e7:90 dev eth1 vlan 10 master br0 
    | aa:c1:ab:b7:d3:52 dev eth1 vlan 20 master br0 permanent
    | aa:c1:ab:b7:d3:52 dev eth1 vlan 10 master br0 permanent
    | aa:c1:ab:b7:d3:52 dev eth1 master br0 permanent
    | 33:33:00:00:00:01 dev eth1 self permanent
    | 01:00:5e:00:00:01 dev eth1 self permanent
    | 33:33:ff:b7:d3:52 dev eth1 self permanent
    | aa:c1:ab:6b:b2:49 dev eth2 vlan 20 master br0 permanent
    | aa:c1:ab:6b:b2:49 dev eth2 master br0 permanent
    | 33:33:00:00:00:01 dev eth2 self permanent
    | 01:00:5e:00:00:01 dev eth2 self permanent
    | 33:33:ff:6b:b2:49 dev eth2 self permanent
E87 +30:56 sw3 exit=0 $ clear
E88 +30:58 sw3 exit=0 $ ls
    | motd
E89 +31:29 host-a exit=2 $ ping 172.20.0.11
    | ping: connect: Network unreachable
E90 +31:30 host-a exit=2 $ ping 172.20.0.12
    | ping: connect: Network unreachable
E91 +31:37 host-a exit=1 $ ping 10.20.0.2
    | PING 10.20.0.2 (10.20.0.2) 56(84) bytes of data.
    | ^C
    | --- 10.20.0.2 ping statistics ---
    | 2 packets transmitted, 0 received, 100% packet loss, time 1003ms
E92 +32:28 sw3 exit=0 $ ip -br link
    | lo               UNKNOWN        00:00:00:00:00:00 <LOOPBACK,UP,LOWER_UP> 
    | br0              UP             aa:c1:ab:6b:b2:49 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | vlan10@br0       UP             aa:c1:ab:6b:b2:49 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | eth1@if130       UP             aa:c1:ab:b7:d3:52 <BROADCAST,MULTICAST,UP,LOWER_UP> 
    | eth2@if135       UP             aa:c1:ab:6b:b2:49 <BROADCAST,MULTICAST,UP,LOWER_UP> 
E93 +32:41 sw3 exit=0 $ bridge link
    | 131: eth1@if130: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 master br0 state forwarding priority 32 cost 2 
    | 134: eth2@if135: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 master br0 state forwarding priority 32 cost 2 
E94 +32:53 sw3 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              20
    | br0               1 PVID Egress Untagged
    |                   10
E95 +33:13 sw3 exit=0 $ bridge fdb show br br0
    | 33:33:00:00:00:01 dev br0 self permanent
    | 01:00:5e:00:00:6a dev br0 self permanent
    | 33:33:00:00:00:6a dev br0 self permanent
    | 01:00:5e:00:00:01 dev br0 self permanent
    | 33:33:ff:6b:b2:49 dev br0 self permanent
    | 01:80:c2:00:00:21 dev br0 self permanent
    | aa:c1:ab:6b:b2:49 dev br0 vlan 10 master br0 permanent
    | aa:c1:ab:6b:b2:49 dev br0 vlan 1 master br0 permanent
    | aa:c1:ab:95:e7:90 dev eth1 vlan 10 master br0 
    | aa:c1:ab:b7:d3:52 dev eth1 vlan 20 master br0 permanent
    | aa:c1:ab:b7:d3:52 dev eth1 vlan 10 master br0 permanent
    | aa:c1:ab:b7:d3:52 dev eth1 master br0 permanent
    | 33:33:00:00:00:01 dev eth1 self permanent
    | 01:00:5e:00:00:01 dev eth1 self permanent
    | 33:33:ff:b7:d3:52 dev eth1 self permanent
    | aa:c1:ab:6b:b2:49 dev eth2 vlan 20 master br0 permanent
    | aa:c1:ab:6b:b2:49 dev eth2 master br0 permanent
    | 33:33:00:00:00:01 dev eth2 self permanent
    | 01:00:5e:00:00:01 dev eth2 self permanent
    | 33:33:ff:6b:b2:49 dev eth2 self permanent
E96 +34:34 sw2 exit=0 $ bridge vlan add dev eth2 vid 20  [UBAH STATE: vlan eth2 20]
E97 +34:39 sw2 exit=2 $ ping 10.20.0.2
    | ping: connect: Network unreachable
E98 +35:09 sw2 exit=127 $ br vlan show
    | bash: br: command not found
E99 +35:14 sw2 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              10
    |                   20
    | br0               1 PVID Egress Untagged
    |                   10
E100 +35:33 host-a exit=1 $ ping 10.20.0.2
    | PING 10.20.0.2 (10.20.0.2) 56(84) bytes of data.
    | ^C
    | --- 10.20.0.2 ping statistics ---
    | 2 packets transmitted, 0 received, 100% packet loss, time 1044ms
E101 +35:42 sw1 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              20
    | eth2              10
    |                   20
    | br0               1 PVID Egress Untagged
    |                   10
E102 +36:02 sw1 exit=0 $ bridge vlan add dev eth1 vid 10  [UBAH STATE: vlan eth1 10]
E103 +36:04 sw1 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              10
    |                   20
    | br0               1 PVID Egress Untagged
    |                   10
E104 +36:42 sw1 exit=2 $ ping 10.20.0.2
    | ping: connect: Network unreachable
E105 +36:52 sw1 exit=2 $ ping 172.20.20.13
    | ping: connect: Network unreachable
E106 +36:53 sw1 exit=2 $ ping 172.20.20.12
    | ping: connect: Network unreachable
E107 +36:55 sw1 exit=2 $ ping 172.20.20.11
    | ping: connect: Network unreachable
E108 +36:57 sw1 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.11/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 128: eth2@if129: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:ed:d4:96 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-86b164db1cbfedde
    |     inet6 fe80::a8c1:abff:feed:d496/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 132: eth1@if133: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff link-netnsid 0
    |     altname clab-o-cc07a502bb1208b9
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E109 +37:11 sw1 exit=0 $ ping 10.10.0.11
    | PING 10.10.0.11 (10.10.0.11) 56(84) bytes of data.
    | 64 bytes from 10.10.0.11: icmp_seq=1 ttl=64 time=0.028 ms
    | ^C
    | --- 10.10.0.11 ping statistics ---
    | 1 packets transmitted, 1 received, 0% packet loss, time 0ms
    | rtt min/avg/max/mdev = 0.028/0.028/0.028/0.000 ms
E110 +37:12 sw1 exit=0 $ ping 10.10.0.12
    | PING 10.10.0.12 (10.10.0.12) 56(84) bytes of data.
    | 64 bytes from 10.10.0.12: icmp_seq=1 ttl=64 time=0.040 ms
    | ^C
    | --- 10.10.0.12 ping statistics ---
    | 1 packets transmitted, 1 received, 0% packet loss, time 0ms
    | rtt min/avg/max/mdev = 0.040/0.040/0.040/0.000 ms
E111 +37:14 sw1 exit=0 $ ping 10.10.0.13
    | PING 10.10.0.13 (10.10.0.13) 56(84) bytes of data.
    | 64 bytes from 10.10.0.13: icmp_seq=1 ttl=64 time=0.092 ms
    | ^C
    | --- 10.10.0.13 ping statistics ---
    | 1 packets transmitted, 1 received, 0% packet loss, time 0ms
    | rtt min/avg/max/mdev = 0.092/0.092/0.092/0.000 ms
E112 +37:41 host-a exit=1 $ ping 10.20.0.2
    | PING 10.20.0.2 (10.20.0.2) 56(84) bytes of data.
    | ^C
    | --- 10.20.0.2 ping statistics ---
    | 2 packets transmitted, 0 received, 100% packet loss, time 1003ms
E113 +41:14 sw2 exit=0 $ clear
E114 +41:14 sw2 exit=0 $ ls
    | motd
E115 +41:15 sw2 exit=0 $ clear
E116 +41:23 sw2 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.12/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 129: eth1@if128: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:0c:1e:d0 brd ff:ff:ff:ff:ff:ff link-netnsid 2
    |     altname clab-o-8a7353bb4e7fb4cd
    |     inet6 fe80::a8c1:abff:fe0c:1ed0/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 130: eth2@if131: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:2f:4f:b4 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-8532426a9c265fe9
    |     inet6 fe80::a8c1:abff:fe2f:4fb4/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E117 +41:31 sw2 exit=255 $ bridge show vlan
    | Object "show" is unknown, try "bridge help".
E118 +41:37 sw2 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              10
    |                   20
    | br0               1 PVID Egress Untagged
    |                   10
E119 +42:14 sw1 exit=0 $ clear
E120 +42:15 sw1 exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 2: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 3: vlan10@br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default qlen 1000
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff
    |     inet 10.10.0.11/24 scope global vlan10
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 128: eth2@if129: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:ed:d4:96 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-86b164db1cbfedde
    |     inet6 fe80::a8c1:abff:feed:d496/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
    | 132: eth1@if133: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue master br0 state UP group default 
    |     link/ether aa:c1:ab:95:e7:90 brd ff:ff:ff:ff:ff:ff link-netnsid 0
    |     altname clab-o-cc07a502bb1208b9
    |     inet6 fe80::a8c1:abff:fe95:e790/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E121 +42:17 sw1 exit=0 $ clear
E122 +42:20 sw1 exit=255 $ bridge show vlan
    | Object "show" is unknown, try "bridge help".
E123 +42:27 sw1 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              10
    |                   20
    | br0               1 PVID Egress Untagged
    |                   10
E124 +44:20 sw3 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              20
    | br0               1 PVID Egress Untagged
    |                   10
E125 +44:41 sw3 exit=255 $ bridge add vlan dev eth2 vid 20 tagged
    | Object "add" is unknown, try "bridge help".
E126 +44:47 sw3 exit=0 $ bridge vlan add dev eth2 vid 20 tagged  [UBAH STATE: vlan eth2 20] [REWORK]
E127 +44:50 sw3 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              20
    | br0               1 PVID Egress Untagged
    |                   10
E128 +44:56 sw3 exit=127 $ exitr
    | bash: exitr: command not found
E129 +45:01 host-a exit=0 $ ls
    | motd
E130 +45:09 host-a exit=1 $ ping 10.20.0.2
    | PING 10.20.0.2 (10.20.0.2) 56(84) bytes of data.
    | ^C
    | --- 10.20.0.2 ping statistics ---
    | 3 packets transmitted, 0 received, 100% packet loss, time 2075ms
E131 +45:19 host-a exit=0 $ ip a
    | 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    |     link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    |     inet 127.0.0.1/8 scope host lo
    |        valid_lft forever preferred_lft forever
    |     inet6 ::1/128 scope host proto kernel_lo 
    |        valid_lft forever preferred_lft forever
    | 133: eth1@if132: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9500 qdisc noqueue state UP group default 
    |     link/ether aa:c1:ab:51:86:74 brd ff:ff:ff:ff:ff:ff link-netnsid 1
    |     altname clab-o-dbc05e4fb5aae78e
    |     inet 10.20.0.1/24 scope global eth1
    |        valid_lft forever preferred_lft forever
    |     inet6 fe80::a8c1:abff:fe51:8674/64 scope link proto kernel_ll 
    |        valid_lft forever preferred_lft forever
E132 +46:03 sw1 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              10
    |                   20
    | br0               1 PVID Egress Untagged
    |                   10
E133 +48:38 sw1 exit=0 $ bridge vlan add dev eth1 vid 20 untagged  [UBAH STATE: vlan eth1 20] [REWORK]
E134 +48:42 sw1 exit=2 $ ping 10.20.0.1
    | ping: connect: Network unreachable
E135 +49:01 sw3 exit=255 $ bridge show vland
    | Object "show" is unknown, try "bridge help".
E136 +49:05 sw3 exit=255 $ bridge vland show
    | Object "vland" is unknown, try "bridge help".
E137 +49:07 sw3 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              20
    | br0               1 PVID Egress Untagged
    |                   10
E138 +49:30 sw3 exit=0 $ bridge vlan add dev eth2 vid 20 untagged  [UBAH STATE: vlan eth2 20] [REWORK]
E139 +49:31 sw3 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              20 Egress Untagged
    | br0               1 PVID Egress Untagged
    |                   10
E140 +49:36 sw3 exit=2 $ ping 10.20.0.1
    | ping: connect: Network unreachable
E141 +50:02 host-a exit=1 $ ping 10.20.0.2
    | PING 10.20.0.2 (10.20.0.2) 56(84) bytes of data.
    | From 10.20.0.1 icmp_seq=1 Destination Host Unreachable
    | From 10.20.0.1 icmp_seq=2 Destination Host Unreachable
    | From 10.20.0.1 icmp_seq=3 Destination Host Unreachable
    | From 10.20.0.1 icmp_seq=5 Destination Host Unreachable
    | From 10.20.0.1 icmp_seq=6 Destination Host Unreachable
    | From 10.20.0.1 icmp_seq=7 Destination Host Unreachable
    | From 10.20.0.1 icmp_seq=8 Destination Host Unreachable
    | From 10.20.0.1 icmp_seq=9 Destination Host Unreachable
    | From 10.20.0.1 icmp_seq=10 Destination Host Unreachable
    | From 10.20.0.1 icmp_seq=11 Destination Host Unreachable
    | From 10.20.0.1 icmp_seq=12 Destination Host Unreachable
    | ^C
    | --- 10.20.0.2 ping statistics ---
    | 13 packets transmitted, 0 received, +11 errors, 100% packet loss, time 12273ms
    | pipe 4
E142 +50:18 sw1 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20 Egress Untagged
    | eth2              10
    |                   20
    | br0               1 PVID Egress Untagged
    |                   10
E143 +51:18 sw2 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              10
    |                   20
    | br0               1 PVID Egress Untagged
    |                   10
E144 +51:54 sw1 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20 Egress Untagged
    | eth2              10
    |                   20
    | br0               1 PVID Egress Untagged
    |                   10
E145 +52:15 sw1 exit=0 $ bridge vlan add dev eth1 vid 20 pvid untagged  [UBAH STATE: vlan eth1 20] [REWORK]
E146 +52:17 sw1 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20 PVID Egress Untagged
    | eth2              10
    |                   20
    | br0               1 PVID Egress Untagged
    |                   10
E147 +52:30 sw3 exit=0 $ bridge vlan show
    | port              vlan-id  
    | eth1              10
    |                   20
    | eth2              20 Egress Untagged
    | br0               1 PVID Egress Untagged
    |                   10
E148 +52:46 sw3 exit=0 $ bridge vlan add dev eth2 vid 20 pvid untagged  [UBAH STATE: vlan eth2 20] [REWORK]
E149 +52:56 host-a exit=0 $ ping 10.20.0.1
    | PING 10.20.0.1 (10.20.0.1) 56(84) bytes of data.
    | 64 bytes from 10.20.0.1: icmp_seq=1 ttl=64 time=0.016 ms
    | ^C
    | --- 10.20.0.1 ping statistics ---
    | 1 packets transmitted, 1 received, 0% packet loss, time 0ms
    | rtt min/avg/max/mdev = 0.016/0.016/0.016/0.000 ms
E150 +52:58 host-a exit=0 $ ping 10.20.0.2
    | PING 10.20.0.2 (10.20.0.2) 56(84) bytes of data.
    | 64 bytes from 10.20.0.2: icmp_seq=1 ttl=64 time=0.083 ms
    | ^C
    | --- 10.20.0.2 ping statistics ---
    | 1 packets transmitted, 1 received, 0% packet loss, time 0ms
    | rtt min/avg/max/mdev = 0.083/0.083/0.083/0.000 ms
E151 +54:31 host-a exit=2 $ ping 10.10.0.11
    | ping: connect: Network unreachable
