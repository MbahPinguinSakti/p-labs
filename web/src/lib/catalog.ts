// Lab yang direncanakan tapi belum ada soalnya di labs/. Tampil sebagai "segera hadir",
// tidak bisa dibuka. Hapus entri di sini begitu soalnya dibuat (judul sama).

export type PlannedLab = {
  title: string;
  category: string;
  difficulty: "beginner" | "intermediate" | "advanced";
  duration_min: number;
};

export const PLANNED_LABS: PlannedLab[] = [
  { title: "STP Root Bridge Salah", category: "networking", difficulty: "intermediate", duration_min: 20 },
  { title: "DHCP Relay Hilang", category: "networking", difficulty: "intermediate", duration_min: 12 },
  { title: "Packet Sniffing", category: "analisis", difficulty: "intermediate", duration_min: 15 },
];

/** Warna sampul kartu per kategori (gradien dari desain). */
export const COVER: Record<string, string> = {
  Networking: "linear-gradient(110deg, #123B2B 0%, #1F7A55 100%)",
  Analisis: "linear-gradient(110deg, #3B2A0C 0%, #C9922A 100%)",
};
