// Klien API platform/server.py. Tipe di sini mengikuti bentuk JSON dari server.

export type Scores = {
  correctness: number | null;
  efficiency: number | null;
  methodology: number | null;
  safety: number | null;
};

export type HistoryEntry = {
  session: string;
  kind: "sessions" | "golden";
  date: number | null;
  duration_s: number;
  commands: number;
  final_score: number | null;
  scores: Scores | null;
  band: string | null;
  label?: string | null;
};

export type LabCard = {
  id: string;
  title: string;
  category: string | null;
  difficulty: string | null;
  nos: string | null;
  duration_min: number | null;
  summary: string | null;
  ticket: string | null;
  sessions: number;
  best_score: number | null;
  active_session: string | null;
  active_started: number | null;
  checkpoints_total: number;
  checkpoints_hit: number;
};

export type TopoNode = { id: string; role: "host" | "switch" | "router" | "firewall" | string; kind?: string };
export type TopoLink = { a: string; a_if: string; b: string; b_if: string; label: string | null };

export type LabDetail = LabCard & {
  brief: { ticket_title: string; markdown: string };
  topology: { nodes: TopoNode[]; links: TopoLink[] };
  weights: Record<string, number>;
  history: HistoryEntry[];
  // Image yang harus dibangun lokal sebelum deploy (mis. RouterOS), beserta perintahnya.
  missing_images: { image: string; build: string | null }[];
};

export type LiveCheckpoint = {
  id: string | null;
  label: string;
  type: "command_match" | "state_check" | "llm_judge";
  hidden: boolean;
  status: "hit" | "miss" | "pending_llm";
  ts?: number;
  node?: string;
  evidence?: string;
};

export type EvalJob = {
  session: string;
  status: "running" | "done" | "error";
  phase: "verify" | "llm" | "rules" | "archive" | "done";
  started: number;
  finished?: number;
  use_llm: boolean;
  error: string | null;
  final_score?: number | null;
};

export type DeployJob = {
  // queued (mode Server): menunggu slot deploy atau RAM; position 1-based di antrian FIFO.
  status: "queued" | "running" | "done" | "error";
  position?: number;
  queue_reason?: "busy" | "memory";
  queued_at?: number;
  step: "destroy" | "deploy" | "verify" | "inject" | "done" | null;
  started: number | null;
  finished?: number;
  error: string | null;
};

export type LiveState = {
  lab: string;
  session: string | null;
  nodes: string[];
  running: string[] | null;
  started?: number | null;
  created?: number | null;
  commands?: number;
  // source: perubahan dari luar terminal (Winbox/WebFig/API), direkam dari konfigurasi router.
  activity?: { id: string; node: string; command: string; ts: number; exit: number | null; state_change: boolean; source?: string | null }[];
  // published: port host yang bisa dibuka dari komputer lain (mode Server, winbox_ports); host = alamat server.
  gui_access?: { node: string; host: string; port: number; user: string; password: string; published?: boolean }[];
  checkpoints?: LiveCheckpoint[];
  hints?: { level: number; penalty: number; opened: boolean; text: string | null }[];
  evaluated?: boolean;
  job?: EvalJob | null;
  deploy?: DeployJob | null;
};

export type Role = "admin" | "guru" | "siswa";

export type User = { username: string; display_name: string; role: Role };

export type Me = {
  // pribadi: tanpa login (user = akun lokal). server: wajib login; user null = belum login.
  mode: "pribadi" | "server";
  // mandiri: semua setara + leaderboard antar-user. kelas: guru melihat progres siswa.
  style: "mandiri" | "kelas";
  auth: boolean;
  user: User | null;
  // llm dan deploy hanya dikirim untuk user yang sudah login (mode Server tanpa
  // login: tidak ada), jadi selalu baca dengan `?.`.
  llm?: { provider: string; model: string | null; missing_env: string[] | null };
  // Bisakah server menjalankan reset.sh tanpa password sudo (lihat platform/setup-sudoless.sh)?
  deploy?: { available: boolean; mode: "setuid" | "sudo" | null; reason: string | null };
};

export type TimelineEntry = {
  id: string;
  t: number;
  node: string;
  command: string;
  exit: number | null;
  source?: string | null;
  state_change: string[];
  rework: string[];
  hint_level?: number | null;
  output?: string | null;
};

export type Evaluation = {
  problem: string;
  session: string;
  weights: Record<string, number>;
  rule_based: {
    correctness: number;
    verify: { correctness: number; ping_ok?: boolean; issues?: string[] };
    efficiency: { score: number; state_changes: number; baseline_changes: number; extra_changes: number; rework_changes: number; change_events: string[] };
    safety: { score: number; violations: { id: string; severity: string; reason: string; events?: string[]; event?: string }[] };
    hints: { levels_used: number[]; penalty: number };
    checkpoints: { id: string; type: string; hit: boolean; event: string | null; ts: number | null }[];
    // waived: gate tidak berlaku karena fix dibuat lewat GUI (lihat platform/guiwatch.py).
    process_gate: { factor: number; required: string[]; before: string; met: string[]; missing: string[]; applies_to: string[]; waived?: string } | null;
    gui?: { used: boolean; via: string[]; changes: string[]; fix_event: string | null; fix_source: string | null };
  };
  llm: {
    methodology: { band: string; score: number; rationale: string; evidence: { event: string; note: string }[] };
    llm_checkpoints: { id: string; hit: boolean; rationale: string; evidence?: unknown }[];
    feedback: {
      summary: string;
      strengths: string[];
      improvements: string[];
      technical_lessons: string[];
      key_moments: { event: string; note: string }[];
      next_practice: string;
    };
  } | null;
  warnings: string[];
  scores: Scores;
  credited: Record<string, number | null>;
  final_score: number | null;
};

export type SessionResult = {
  kind: "sessions" | "golden";
  result: Evaluation;
  timeline: TimelineEntry[];
  checkpoint_labels: Record<string, string>;
  title: string;
  date: number | null;
  duration_s: number;
  label: string | null;
};

export type ProgressData = { sessions: (HistoryEntry & { lab: string; title: string })[]; points: number };

export type LeaderEntry = {
  rank: number;
  name: string;
  you: boolean;
  // Mode server: username user lain (tidak ada untuk entri anonim di gaya kelas).
  username?: string;
  anonymous?: boolean;
  golden?: boolean;
  lab?: string;
  session?: string;
  points: number;
  labs: number;
  methodology_avg: number | null;
};

// --- dashboard (mode Server). Kontrak: platform/admin_accounts.py, admin_labs.py, class_api.py

export type AdminUser = User & { active: boolean; created_at: number; last_seen: number | null };

export type ImportResult = {
  created: { username: string; password: string | null }[];
  errors: { line: number; message: string }[];
};

export type AdminLab = {
  lab_id: string;
  title: string;
  username: string;
  display_name: string;
  clab_name: string;
  mem_mb: number;
  state: "running" | "deploying" | "stopped";
  deploy_step: DeployJob["step"];
  session: string | null;
  last_activity: number | null;
  idle_s: number | null;
  busy: "deploy" | "evaluate" | "stop" | null;
};

export type AdminQueueEntry = {
  username: string;
  display_name: string;
  lab_id: string;
  title: string;
  position: number;
  reason: "busy" | "memory";
  queued_at: number;
};

export type AdminLabs = {
  capacity: { used_mb: number; limit_mb: number; deploying: number; max_deploys: number; idle_minutes: number };
  labs: AdminLab[];
  queue: AdminQueueEntry[];
};

export type ClassStudent = {
  username: string;
  display_name: string;
  points: number;
  sessions: number;
  best_scores: Record<string, number>;
  attempts: Record<string, number>;
  last_session: number | null;
};

export type ClassProgress = { labs: { id: string; title: string }[]; students: ClassStudent[] };

export type StudentDetail = { student: User; points: number; sessions: ProgressData["sessions"] };

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Dikirim saat server menjawab 401 (sesi login habis / logout di tab lain).
// AppDataProvider mendengarkannya dan memuat ulang /api/me, sehingga halaman Login muncul.
export const UNAUTHORIZED_EVENT = "plab:unauthorized";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  if (res.status === 401 && path !== "/auth/login") {
    // 401 dari login = password salah, ditampilkan di form; selain itu = belum/tidak lagi login.
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* respons bukan JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  me: () => request<Me>("GET", "/me"),
  login: (username: string, password: string) =>
    request<{ user: User }>("POST", "/auth/login", { username, password }),
  logout: () => request<{ ok: boolean }>("POST", "/auth/logout"),
  labs: () => request<LabCard[]>("GET", "/labs"),
  lab: (id: string) => request<LabDetail>("GET", `/labs/${id}`),
  session: (id: string) => request<LiveState>("GET", `/labs/${id}/session`),
  // Hanya checkpoint watcher; terminal lewat WebSocket /api/labs/{id}/term/{node} (termbridge.py).
  runtime: (id: string) => request<{ watcher: boolean }>("POST", `/labs/${id}/runtime`),
  hint: (id: string, level?: number) =>
    request<{ level: number; text: string; penalty: number; new: boolean }>("POST", `/labs/${id}/hint`, { level: level ?? null }),
  deploy: (id: string) => request<DeployJob>("POST", `/labs/${id}/deploy`),
  cancelDeploy: (id: string) => request<{ ok: boolean }>("DELETE", `/labs/${id}/deploy`),
  start: (id: string) => request<{ session: string; new: boolean }>("POST", `/labs/${id}/start`),
  evaluate: (id: string, useLlm: boolean) => request<EvalJob>("POST", `/labs/${id}/evaluate`, { use_llm: useLlm }),
  result: (id: string, session: string) => request<SessionResult>("GET", `/labs/${id}/sessions/${session}`),
  progress: () => request<ProgressData>("GET", "/progress"),
  leaderboard: () => request<LeaderEntry[]>("GET", "/leaderboard"),
  // admin
  adminUsers: () => request<{ users: AdminUser[] }>("GET", "/admin/users"),
  adminCreateUser: (body: { username: string; display_name?: string; role: Role; password?: string }) =>
    request<{ user: AdminUser; password: string | null }>("POST", "/admin/users", body),
  adminImportUsers: (csv: string, defaultRole: Role = "siswa") =>
    request<ImportResult>("POST", "/admin/users/import", { csv, default_role: defaultRole }),
  adminUpdateUser: (username: string, body: { display_name?: string; role?: Role; active?: boolean }) =>
    request<{ user: AdminUser; stopped_labs: string[]; skipped_labs: string[] }>("PATCH", `/admin/users/${username}`, body),
  adminResetPassword: (username: string, password?: string) =>
    request<{ password: string | null }>("POST", `/admin/users/${username}/password`, { password: password || null }),
  adminLabs: () => request<AdminLabs>("GET", "/admin/labs"),
  adminStopLab: (username: string, labId: string) =>
    request<{ ok: boolean; archived: string | null }>("POST", `/admin/labs/${username}/${labId}/stop`),
  // guru (gaya kelas)
  classProgress: () => request<ClassProgress>("GET", "/class/progress"),
  classStudent: (username: string) => request<StudentDetail>("GET", `/class/students/${username}`),
  classSession: (username: string, labId: string, session: string) =>
    request<SessionResult>("GET", `/class/students/${username}/labs/${labId}/sessions/${session}`),
};

// Unduhan CSV nilai kelas (link biasa: cookie ikut terkirim).
export const CLASS_EXPORT_URL = "/api/class/export.csv";
