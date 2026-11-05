// Materi tipis per jalur Belajar: ringkasan konsep + satu lab untuk praktik.
// `lab` dicocokkan ke judul soal di labs/; kalau soalnya belum ada, tampil "segera hadir".

export type Module = { title: string; body: string; lab?: string; read: number; note?: string };
export type SideItem = { term: string; desc: string; code?: boolean };
export type Track = {
  title: string;
  intro: string;
  modules: Module[];
  scope: string; // teks setelah jumlah modul, mis. "berlaku di semua lab"
  side: { title: string; subtitle?: string; items: SideItem[] }[];
};

export const TRACKS: Record<string, Track> = {
  networking: {
    title: "Networking",
    intro:
      "Dasar jaringan yang paling sering muncul di tiket nyata: VLAN, spanning tree, routing, dan layanan seperti DHCP. Tiap modul berisi ringkasan singkat, lalu satu lab untuk praktik langsung.",
    scope: "lab terkait",
    modules: [
      {
        title: "VLAN dan trunk",
        body: "VLAN memecah satu switch menjadi beberapa domain broadcast. Port akses membawa satu VLAN tanpa tag, trunk membawa banyak VLAN dengan tag 802.1Q. Di Linux bridge, port akses butuh pvid dan untagged sekaligus.",
        lab: "VLAN Trunk Misconfiguration",
        read: 4,
      },
      {
        title: "Spanning tree",
        body: "STP mencegah loop L2 dengan memilih satu root bridge dan memblokir jalur cadangan. Root dipilih dari bridge ID terkecil (prioritas, lalu MAC), jadi prioritas yang salah bisa memindahkan root ke switch akses.",
        lab: "STP Root Bridge Salah",
        read: 5,
      },
      {
        title: "Subnetting dan routing statis",
        body: "Prefix /24 berisi 256 alamat dan 254 di antaranya bisa dipakai host. Router memilih rute dengan prefix terpanjang yang cocok, lalu meneruskan paket ke next-hop di tabel routing.",
        lab: "Subnetting Dasar",
        read: 5,
      },
      {
        title: "OSPF",
        body: "Dua router baru menjadi neighbor OSPF kalau area, hello/dead interval, dan MTU-nya cocok. Neighbor yang macet di EXSTART hampir selalu disebabkan MTU yang berbeda.",
        lab: "OSPF Neighbor Stuck",
        read: 6,
      },
      {
        title: "DHCP dan relay",
        body: "Permintaan DHCP berupa broadcast, jadi tidak menembus router. DHCP relay meneruskannya sebagai unicast ke server DHCP di subnet lain.",
        lab: "DHCP Relay Hilang",
        read: 4,
      },
    ],
    side: [
      {
        title: "Contekan perintah",
        subtitle: "Lab memakai Linux bridge.",
        items: [
          { term: "bridge vlan show", desc: "VLAN yang dibawa tiap port, plus PVID dan untagged", code: true },
          { term: "ip -br addr", desc: "Alamat IP per interface, satu baris per interface", code: true },
          { term: "ip neigh", desc: "Tabel ARP. INCOMPLETE berarti tidak ada balasan L2", code: true },
          { term: "ip route", desc: "Tabel routing dan next-hop", code: true },
          { term: "ping -c 3 -W 1 <ip>", desc: "Uji jangkauan dengan batas waktu 1 detik", code: true },
        ],
      },
      {
        title: "Padanan perintah vendor",
        subtitle: "Untuk yang terbiasa dengan Cisco IOS.",
        items: [
          { term: "show vlan brief", desc: "≈ bridge vlan show", code: true },
          { term: "show interfaces trunk", desc: "≈ bridge -d vlan show", code: true },
          { term: "show ip interface brief", desc: "≈ ip -br addr", code: true },
        ],
      },
    ],
  },
  cybersecurity: {
    title: "Cybersecurity",
    intro:
      "Keamanan jaringan dari dua sisi: bertahan, dan menyerang di dalam scope yang diizinkan. Fokusnya membaca trafik, aturan firewall, dan celah dasar layanan web.",
    scope: "lab terkait",
    modules: [
      {
        title: "Firewall dan ACL",
        body: "Aturan dibaca dari atas ke bawah dan berhenti di aturan pertama yang cocok. Aturan deny yang terlalu luas di atas akan menutup aturan allow di bawahnya.",
        lab: "Firewall Rules",
        read: 4,
      },
      {
        title: "Analisis paket",
        body: "Capture dengan tcpdump, lalu saring per protokol dan port. Handshake TCP yang berhenti di SYN berarti balasan diblokir atau tidak pernah sampai.",
        lab: "Packet Sniffing",
        read: 5,
      },
      {
        title: "DNS dan ACL",
        body: "Kalau ping ke IP berhasil tapi ke nama gagal, cek resolusi DNS dulu. ACL yang memblokir UDP 53 sering jadi penyebab yang terlewat.",
        lab: "ACL Memblokir DNS",
        read: 4,
      },
      {
        title: "Web exploit dasar",
        body: "Input yang tidak divalidasi bisa mengubah query atau perintah di server. Kerjakan hanya pada target yang tertulis di brief lab.",
        lab: "Web Exploit Dasar",
        read: 6,
      },
      {
        title: "Hardening layanan",
        body: "Matikan layanan yang tidak dipakai, batasi port yang terbuka, dan ganti kredensial bawaan. Setiap port terbuka menambah permukaan serangan.",
        read: 4,
        note: "Lab segera hadir",
      },
    ],
    side: [
      {
        title: "Contekan perintah",
        items: [
          { term: "tcpdump -ni eth1 port 53", desc: "Lihat trafik DNS di satu interface", code: true },
          { term: "nft list ruleset", desc: "Aturan firewall yang sedang aktif", code: true },
          { term: "ss -tulpn", desc: "Port yang sedang listen dan prosesnya", code: true },
          { term: "dig @<server> <nama>", desc: "Uji resolusi ke server DNS tertentu", code: true },
        ],
      },
      {
        title: "Aturan scope",
        subtitle: "Pelanggaran dicatat sebagai safety dan memotong skor.",
        items: [
          { term: "Hanya target di brief", desc: "Host di luar daftar tidak boleh dipindai atau diserang." },
          { term: "Tanpa DoS", desc: "Jangan membanjiri layanan, walaupun targetnya sah." },
          { term: "Jangan merusak data", desc: "Bukti cukup dengan membaca, bukan menghapus." },
        ],
      },
    ],
  },
  "problem-solving": {
    title: "Problem Solving",
    intro:
      "Cara berpikir yang sama untuk semua soal, apa pun perangkatnya. Inilah yang dinilai evaluator sebagai methodology, dan bobotnya paling besar di lab troubleshooting.",
    scope: "berlaku di semua lab",
    modules: [
      {
        title: "Baca gejala dengan tepat",
        body: "Ulangi masalahnya dengan kata-kata sendiri: siapa tidak bisa menjangkau siapa, sejak kapan, dan apa yang masih berfungsi. Yang masih berfungsi sering jadi petunjuk terbesar.",
        read: 3,
        note: "Dipakai di semua lab",
      },
      {
        title: "Isolasi per lapisan",
        body: "Mulai dari bawah lalu naik: link, VLAN, ARP, IP, routing, layanan. Bandingkan dengan jalur yang masih jalan, misalnya VLAN 10 jalan sedangkan VLAN 20 tidak.",
        lab: "VLAN Trunk Misconfiguration",
        read: 4,
      },
      {
        title: "Hipotesis sebelum mengubah",
        body: 'Tulis satu kalimat: "saya kira X karena Y". Perubahan tanpa hipotesis dibaca sebagai trial-and-error dan menurunkan skor methodology.',
        read: 3,
      },
      {
        title: "Satu perubahan, satu verifikasi",
        body: "Ubah satu hal, lalu cek hasilnya sebelum menyentuh hal lain. Dengan begitu kamu tahu perubahan mana yang memperbaiki dan mana yang merusak.",
        read: 3,
      },
      {
        title: "Hindari kerusakan tambahan",
        body: "Jangan menyentuh perangkat sehat tanpa bukti, dan jangan mematikan fitur pengaman demi jalan pintas. Fix yang merusak desain hanya mendapat correctness 50.",
        read: 3,
      },
    ],
    side: [
      {
        title: "Cara skor dihitung",
        subtitle: "Bobot untuk lab troubleshooting seperti net-001.",
        items: [
          { term: "Correctness · 30%", desc: "Dicek otomatis: masalah selesai dan desain tetap utuh." },
          { term: "Efficiency · 20%", desc: "Jumlah perubahan state dibanding expert. Command baca tidak dihitung." },
          { term: "Methodology · 40%", desc: "Dinilai AI dari urutan langkahmu, dengan bukti per event." },
          { term: "Safety · 10%", desc: "Dipotong kalau menyentuh perangkat sehat atau mematikan pengaman." },
        ],
      },
      {
        title: "Process gate",
        items: [
          {
            term: "Diagnosis dulu, baru fix",
            desc: "Correctness dan efficiency hanya dihitung penuh kalau diagnosis terjadi sebelum fix. Langsung fix tanpa melihat apa pun = keduanya 0.",
          },
        ],
      },
    ],
  },
};
