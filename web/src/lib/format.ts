// Format tampilan: Bahasa Indonesia, pemisah meta "·", angka dengan pemisah ribuan.

const nf = new Intl.NumberFormat("en-US"); // desain memakai koma ribuan: 1,480
export const num = (value: number) => nf.format(value);

export function score(value: number | null | undefined, digits = 1) {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

export function clock(seconds: number) {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${String(m).padStart(2, "0")}:${ss}`;
}

export function minutes(seconds: number) {
  const m = Math.round(seconds / 60);
  return m < 1 ? "<1 menit" : `${m} menit`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];

export function date(epoch: number | null | undefined, withYear = true) {
  if (!epoch) return "—";
  const d = new Date(epoch * 1000);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}${withYear ? ` ${d.getFullYear()}` : ""}`;
}

export const CATEGORY: Record<string, string> = {
  "network-engineer": "Networking",
  "network-admin": "Networking",
  networking: "Networking",
  "cyber-security": "Security",
  security: "Security",
  "problem-solving": "Problem Solving",
  analisis: "Analisis",
};

export const DIFFICULTY: Record<string, string> = {
  beginner: "Pemula",
  intermediate: "Menengah",
  advanced: "Sulit",
};

export const category = (value: string | null | undefined) => (value && CATEGORY[value]) || value || "";
export const difficulty = (value: string | null | undefined) => (value && DIFFICULTY[value]) || value || "";

export const DIMENSIONS = ["correctness", "efficiency", "methodology", "safety"] as const;
export const DIMENSION_LABEL: Record<string, string> = {
  correctness: "Correctness",
  efficiency: "Efficiency",
  methodology: "Methodology",
  safety: "Safety",
};

export const BAND_LABEL: Record<string, string> = {
  sistematis: "sistematis",
  baik: "baik",
  campuran: "campuran",
  trial_and_error: "trial-and-error",
  tanpa_metode: "tanpa metode",
};
export const band = (value: string | null | undefined) => (value ? BAND_LABEL[value] || value : "tanpa AI");
