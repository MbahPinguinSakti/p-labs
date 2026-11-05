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
  status: "running" | "done" | "error";
  step: "destroy" | "deploy" | "verify" | "inject" | "done" | null;
  started: number;
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
  activity?: { id: string; node: string; command: string; ts: number; exit: number | null; state_change: boolean }[];
  checkpoints?: LiveCheckpoint[];
  hints?: { level: number; penalty: number; opened: boolean; text: string | null }[];
  evaluated?: boolean;
  job?: EvalJob | null;
  deploy?: DeployJob | null;
};

export type Me = {
  user: string;
  llm: { provider: string; model: string | null; missing_env: string[] | null };
  // Bisakah server menjalankan reset.sh tanpa password sudo (lihat platform/setup-sudoless.sh)?
  deploy: { available: boolean; mode: "setuid" | "sudo" | null; reason: string | null };
};

export type TimelineEntry = {
  id: string;
  t: number;
  node: string;
  command: string;
  exit: number | null;
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
    process_gate: { factor: number; required: string[]; before: string; met: string[]; missing: string[]; applies_to: string[] } | null;
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
  golden?: boolean;
  lab?: string;
  session?: string;
  points: number;
  labs: number;
  methodology_avg: number | null;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
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
  labs: () => request<LabCard[]>("GET", "/labs"),
  lab: (id: string) => request<LabDetail>("GET", `/labs/${id}`),
  session: (id: string) => request<LiveState>("GET", `/labs/${id}/session`),
  runtime: (id: string) => request<{ ttyd_port: number; ttyd: boolean; ttyd_available: boolean; watcher: boolean }>("POST", `/labs/${id}/runtime`),
  hint: (id: string, level?: number) =>
    request<{ level: number; text: string; penalty: number; new: boolean }>("POST", `/labs/${id}/hint`, { level: level ?? null }),
  deploy: (id: string) => request<DeployJob>("POST", `/labs/${id}/deploy`),
  start: (id: string) => request<{ session: string; new: boolean }>("POST", `/labs/${id}/start`),
  evaluate: (id: string, useLlm: boolean) => request<EvalJob>("POST", `/labs/${id}/evaluate`, { use_llm: useLlm }),
  result: (id: string, session: string) => request<SessionResult>("GET", `/labs/${id}/sessions/${session}`),
  progress: () => request<ProgressData>("GET", "/progress"),
  leaderboard: () => request<LeaderEntry[]>("GET", "/leaderboard"),
};
