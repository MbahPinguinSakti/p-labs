// Lab yang direncanakan tapi belum ada soalnya di labs/. Tampil sebagai "segera hadir",
// tidak bisa dibuka. Hapus entri di sini begitu soalnya dibuat (judul sama).

export type PlannedLab = {
  title: string;
  category: string;
  difficulty: "beginner" | "intermediate" | "advanced";
  duration_min: number;
};

export const PLANNED_LABS: PlannedLab[] = [
  { title: "Subnetting Dasar", category: "networking", difficulty: "beginner", duration_min: 10 },
  { title: "STP Root Bridge Salah", category: "problem-solving", difficulty: "intermediate", duration_min: 20 },
  { title: "OSPF Neighbor Stuck", category: "networking", difficulty: "advanced", duration_min: 15 },
  { title: "DHCP Relay Hilang", category: "networking", difficulty: "intermediate", duration_min: 12 },
  { title: "Firewall Rules", category: "security", difficulty: "intermediate", duration_min: 12 },
  { title: "ACL Memblokir DNS", category: "security", difficulty: "intermediate", duration_min: 10 },
  { title: "Packet Sniffing", category: "analisis", difficulty: "intermediate", duration_min: 15 },
  { title: "Web Exploit Dasar", category: "security", difficulty: "beginner", duration_min: 15 },
];

/** Warna sampul kartu per kategori (gradien dari desain). */
export const COVER: Record<string, string> = {
  Networking: "linear-gradient(110deg, #123B2B 0%, #1F7A55 100%)",
  Security: "linear-gradient(110deg, #3A1A0E 0%, #D4561F 100%)",
  Analisis: "linear-gradient(110deg, #3B2A0C 0%, #C9922A 100%)",
  "Problem Solving": "linear-gradient(110deg, #1B2B44 0%, #2D6A92 100%)",
};
