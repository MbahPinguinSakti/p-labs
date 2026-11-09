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
      {
        title: "MikroTik RouterOS",
        subtitle: "Dipakai lab Subnetting Dasar dan OSPF Neighbor Stuck.",
        items: [
          { term: "/ip address print", desc: "Alamat per interface, lengkap dengan prefix", code: true },
          { term: "/ip route print", desc: "Tabel routing. Flag D = dinamis (mis. OSPF), S = statis", code: true },
          { term: "/routing ospf neighbor print", desc: "Tetangga OSPF dan state-nya (harus Full)", code: true },
          { term: "/interface print", desc: "Status interface, termasuk MTU", code: true },
        ],
      },
    ],
  },
};
