import { marked } from "marked";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Icon } from "../components/Icon";
import { PageHeader } from "../components/Layout";
import { Modal } from "../components/Modal";
import { layers, Topology } from "../components/Topology";
import { api, ApiError, type LabDetail, type LiveCheckpoint, type LiveState } from "../lib/api";
import { useAppData } from "../lib/appData";
import { category, clock, date } from "../lib/format";
import { useApi, useLiveSession, useNow } from "../lib/hooks";
import s from "./LabSession.module.css";

// Halaman Sesi Lab: tiket + checkpoint + hint | terminal per node (ttyd) | topologi + aktivitas.
// State live datang dari WebSocket (/api/labs/:id/ws); server hanya mengirim yang
// boleh dilihat pemain (tanpa ground truth, tanpa teks hint yang belum dibuka).

export function LabSession() {
  const { labId = "" } = useParams();
  const detail = useApi(() => api.lab(labId), [labId]);
  const { state, connected } = useLiveSession(labId);

  if (detail.error) {
    return (
      <>
        <PageHeader title="Lab tidak ditemukan" />
        <p className="notice notice-ember">{detail.error.message}</p>
      </>
    );
  }
  if (!detail.data || !state) return <PageHeader title="Memuat lab…" />;

  const live = Boolean(state.session && !state.evaluated);
  return live ? (
    <ActiveSession lab={detail.data} state={state} connected={connected} />
  ) : (
    <StartSession lab={detail.data} state={state} />
  );
}

function Header({ lab, actions }: { lab: LabDetail; actions?: React.ReactNode }) {
  return (
    <PageHeader
      overline={
        <>
          <Link to="/labs">Labs</Link> · {lab.id} · {category(lab.category)}
        </>
      }
      title={lab.title}
      actions={actions}
    />
  );
}

function Ticket({ lab }: { lab: LabDetail }) {
  const html = useMemo(() => marked.parse(lab.brief.markdown, { async: false, breaks: true }) as string, [lab.brief.markdown]);
  return (
    <section className="panel" aria-labelledby="ticket-title">
      {lab.ticket && <span className="chip">Tiket {lab.ticket}</span>}
      <h2 id="ticket-title" className={s.ticketTitle}>
        {lab.brief.ticket_title}
      </h2>
      {/* brief.md berasal dari repo soal lokal (tepercaya), bukan input pengguna. */}
      <div className={s.brief} dangerouslySetInnerHTML={{ __html: html }} />
    </section>
  );
}

// --- sebelum / sesudah sesi -----------------------------------------------------------

function StartSession({ lab, state }: { lab: LabDetail; state: LiveState }) {
  const navigate = useNavigate();
  const { me, reloadLabs } = useAppData();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deployed = state.running && state.running.length === state.nodes.length;
  const deployJob = state.deploy;
  const deploying = deployJob?.status === "running";
  const canDeploy = me?.deploy.available ?? false;

  const call = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await reloadLabs();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  const start = () => call(() => api.start(lab.id));
  const deploy = () => call(() => api.deploy(lab.id));

  // Tanpa containerlab sudo-less, deploy tetap lewat terminal.
  const manual = (
    <div className="notice">
      <span>
        Deploy dari terminal (containerlab butuh sudo):
        <br />
        <code>cd labs/{lab.id} && ./reset.sh</code>
        {me?.deploy.reason && (
          <>
            <br />
            <span className="soft">Supaya bisa dari sini: {me.deploy.reason}</span>
          </>
        )}
      </span>
    </div>
  );

  return (
    <>
      <Header lab={lab} />
      {state.evaluated && state.session && (
        <div className={`notice ${s.banner}`}>
          <Icon name="check" className="accent" />
          <span>
            Sesi {state.session} sudah dinilai.{" "}
            <button type="button" className="accent" onClick={() => navigate(`/labs/${lab.id}/sesi/${state.session}`)}>
              Lihat hasil evaluasi
            </button>
          </span>
        </div>
      )}
      <div className={s.startGrid}>
        <Ticket lab={lab} />
        <section className="panel">
          <div className="panel-head">
            <h2>Topologi</h2>
            <span className="panel-meta">{lab.nos}</span>
          </div>
          <div className={s.topoScroll}>
            <Topology nodes={lab.topology.nodes} links={lab.topology.links} running={state.running} />
          </div>
        </section>
        <section className={`panel ${s.startPanel}`}>
          <h2 className={s.startTitle}>{state.evaluated ? "Main lagi" : "Mulai sesi"}</h2>
          <p className="soft">
            Semua command di terminal direkam dan dinilai: correctness dicek otomatis, methodology dinilai AI dari
            urutan langkahmu. Hint tersedia, tapi memotong skor.
          </p>
          {state.running === null && (
            <p className="notice notice-ember">Docker tidak bisa diakses dari server. Cek grup docker.</p>
          )}
          {deploying ? (
            <DeployProgress job={deployJob!} />
          ) : deployed ? (
            <button type="button" className="btn btn-primary" onClick={start} disabled={busy}>
              {busy ? "Menyiapkan lab…" : state.evaluated ? "Mulai sesi baru" : "Mulai sesi"}
            </button>
          ) : (
            state.running !== null &&
            (canDeploy ? (
              <>
                <p>Lab belum berjalan. Deploy menyalakan semua node lalu memasang fault (±30 detik).</p>
                <button type="button" className="btn btn-primary" onClick={deploy} disabled={busy}>
                  Deploy & mulai
                </button>
              </>
            ) : (
              <>
                <p>Lab belum berjalan.</p>
                {manual}
              </>
            ))
          )}
          {deployJob?.status === "error" && !deploying && (
            <div className="notice notice-ember">
              <span>
                Deploy gagal.
                {deployJob.error && <pre className={s.deployLog}>{deployJob.error}</pre>}
              </span>
            </div>
          )}
          {error && !deploying && (
            <div className="notice notice-ember">
              <span>{error}</span>
            </div>
          )}
          {/* Lab jalan tapi rusak (rearm ditolak): tawarkan deploy ulang. */}
          {error && deployed && !deploying &&
            (canDeploy ? (
              <button type="button" className="btn btn-secondary" onClick={deploy} disabled={busy}>
                Deploy ulang lab
              </button>
            ) : (
              manual
            ))}
          {lab.history.length > 0 && (
            <div className={s.history}>
              <p className="overline">Sesi sebelumnya</p>
              {lab.history
                .slice()
                .reverse()
                .slice(0, 4)
                .map((h) => (
                  <Link key={h.session} to={`/labs/${lab.id}/sesi/${h.session}`} className={s.historyRow}>
                    <span>{date(h.date)}</span>
                    <span className="soft">{h.final_score ?? "—"}</span>
                    <Icon name="arrow" size={16} />
                  </Link>
                ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}

const DEPLOY_STEPS: [string, string][] = [
  ["destroy", "Membersihkan lab lama"],
  ["deploy", "Menyalakan node (containerlab)"],
  ["verify", "Memeriksa lab sehat"],
  ["inject", "Memasang fault"],
];

function DeployProgress({ job }: { job: NonNullable<LiveState["deploy"]> }) {
  const now = useNow(true);
  const current = DEPLOY_STEPS.findIndex(([id]) => id === job.step);
  return (
    <div className={s.deploySteps}>
      <ol>
        {DEPLOY_STEPS.map(([id, label], i) => (
          <li key={id} className={i < current ? s.stepDone : i === current ? s.stepNow : undefined}>
            {i < current ? <Icon name="check" size={16} /> : i === current ? <span className="dot dot-live" /> : <span className={s.stepIdle} />}
            {label}
          </li>
        ))}
      </ol>
      <p className="soft">{clock(now - job.started)}</p>
    </div>
  );
}

// --- sesi berjalan --------------------------------------------------------------------

function ActiveSession({ lab, state, connected }: { lab: LabDetail; state: LiveState; connected: boolean }) {
  const navigate = useNavigate();
  const { me } = useAppData();
  // Urutan tab mengikuti topologi (host-a → … → host-b), bukan urutan di .clab.yaml.
  const order = useMemo(() => {
    const flat = layers(lab.topology.nodes, lab.topology.links).flat();
    return [...flat.filter((n) => state.nodes.includes(n)), ...state.nodes.filter((n) => !flat.includes(n))];
  }, [lab.topology, state.nodes]);
  const [node, setNode] = useState(() => order[0]);
  const [opened, setOpened] = useState<string[]>([node]);
  const [runtime, setRuntime] = useState<{ port: number; ok: boolean; error?: string } | null>(null);
  const [dialog, setDialog] = useState<null | "hint" | "finish" | "reset">(null);
  const job = state.job;
  const running = job?.status === "running";
  const now = useNow(!running);

  // ttyd + watcher dijalankan server untuk sesi ini (idempoten).
  useEffect(() => {
    let cancelled = false;
    api
      .runtime(lab.id)
      .then((r) => !cancelled && setRuntime({ port: r.ttyd_port, ok: r.ttyd, error: r.ttyd_available ? undefined : "ttyd belum terinstall" }))
      .catch((err) => !cancelled && setRuntime({ port: 0, ok: false, error: String(err.message ?? err) }));
    return () => {
      cancelled = true;
    };
  }, [lab.id, state.session]);

  useEffect(() => {
    if (job?.status === "done") navigate(`/labs/${lab.id}/sesi/${job.session}`);
  }, [job?.status, job?.session, lab.id, navigate]);

  const select = (id: string) => {
    setNode(id);
    setOpened((list) => (list.includes(id) ? list : [...list, id]));
  };
  const elapsed = state.started ? now - state.started : 0;
  const nextHint = state.hints?.find((h) => !h.opened) ?? null;

  return (
    <>
      <Header
        lab={lab}
        actions={
          <>
            <span className={s.timer} title="Waktu sejak command pertama">
              <Icon name="clock" size={18} />
              {state.started ? clock(elapsed) : "00:00"}
            </span>
            <button type="button" className="btn btn-secondary" onClick={() => setDialog("reset")} disabled={running}>
              Reset lab
            </button>
            <button type="button" className="btn btn-secondary" disabled={!nextHint} onClick={() => setDialog("hint")}>
              {nextHint ? "Minta hint" : "Hint habis"}
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setDialog("finish")}>
              Selesai &amp; nilai
            </button>
          </>
        }
      />

      <div className={s.grid}>
        <div className={s.col}>
          <Ticket lab={lab} />
          <Checkpoints items={state.checkpoints ?? []} started={state.started ?? null} />
          <Hints state={state} onOpen={() => setDialog("hint")} />
        </div>

        <section className={s.terminal} aria-label="Terminal">
          <div className={s.termTabs} role="tablist" aria-label="Node">
            {order.map((n) => (
              <button
                key={n}
                type="button"
                role="tab"
                className={`tab ${s.termTab}`}
                aria-selected={node === n}
                onClick={() => select(n)}
                disabled={state.running ? !state.running.includes(n) : false}
              >
                {n}
              </button>
            ))}
          </div>
          <div className={s.termBody}>
            {runtime?.ok ? (
              // Satu iframe per node yang pernah dibuka: shell tetap hidup saat pindah tab.
              opened.map((n) => (
                <iframe
                  key={`${state.session}-${n}`}
                  title={`Terminal ${n}`}
                  src={`http://${location.hostname}:${runtime.port}/?arg=${encodeURIComponent(n)}`}
                  className={s.frame}
                  hidden={n !== node}
                />
              ))
            ) : (
              <div className={s.termEmpty}>
                {runtime?.error ? (
                  <p className="notice notice-ember">Terminal tidak bisa dijalankan: {runtime.error}</p>
                ) : (
                  <p className="soft">Menyiapkan terminal…</p>
                )}
              </div>
            )}
          </div>
          <footer className={s.termFoot}>
            <span className={`dot ${connected ? "dot-live" : ""}`} style={connected ? undefined : { background: "var(--color-ember)" }} />
            {connected ? "Merekam" : "Terputus dari server"} · {state.commands ?? 0} command · sesi {state.session}
          </footer>
        </section>

        <div className={s.col}>
          <section className="panel">
            <div className="panel-head">
              <h2>Topologi</h2>
              <span className="panel-meta">klik node = buka terminal</span>
            </div>
            <div className={s.topoScroll}>
              <Topology
                nodes={lab.topology.nodes}
                links={lab.topology.links}
                selected={node}
                running={state.running}
                onSelect={select}
              />
            </div>
          </section>
          <Activity state={state} />
        </div>
      </div>

      {dialog === "hint" && nextHint && (
        <HintDialog labId={lab.id} level={nextHint.level} penalty={nextHint.penalty} onClose={() => setDialog(null)} />
      )}
      {(dialog === "finish" || running) && (
        <FinishDialog
          labId={lab.id}
          state={state}
          llmMissing={me?.llm.missing_env ?? null}
          provider={me?.llm.provider ?? ""}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "reset" && <ResetDialog lab={lab} onClose={() => setDialog(null)} />}
    </>
  );
}

// Reset = deploy ulang dari nol. Dipakai kalau lab rusak (mis. bridge hilang setelah
// container restart) atau pemain ingin mengulang; sesi berjalan dibuang tanpa dinilai.
function ResetDialog({ lab, onClose }: { lab: LabDetail; onClose: () => void }) {
  const { me } = useAppData();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const support = me?.deploy;

  const reset = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.deploy(lab.id); // state live berpindah ke progres deploy lewat WebSocket
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Reset lab?"
      onClose={onClose}
      actions={
        <>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Batal
          </button>
          {support?.available && (
            <button type="button" className="btn btn-primary btn-sm" onClick={reset} disabled={busy}>
              {busy ? "Memulai…" : "Reset lab"}
            </button>
          )}
        </>
      }
    >
      <p>
        Semua node di-deploy ulang dan fault dipasang lagi (±30 detik). Sesi ini dibuang tanpa dinilai, termasuk
        rekaman command dan hint yang sudah dibuka.
      </p>
      {!support?.available && (
        <p className="notice">
          <span>
            Jalankan dari terminal: <code>cd labs/{lab.id} && ./reset.sh</code>
            {support?.reason && (
              <>
                <br />
                <span className="soft">Supaya bisa dari sini: {support.reason}</span>
              </>
            )}
          </span>
        </p>
      )}
      {error && (
        <p className="notice notice-ember">
          <span>{error}</span>
        </p>
      )}
    </Modal>
  );
}

function Checkpoints({ items, started }: { items: LiveCheckpoint[]; started: number | null }) {
  const counted = items.filter((c) => c.type !== "llm_judge");
  const hit = counted.filter((c) => c.status === "hit").length;
  const at = (ts?: number) => (ts && started ? clock(ts - started) : "");
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Checkpoint</h2>
        <span className="panel-meta">
          {hit} dari {counted.length}
        </span>
      </div>
      <ul className={s.checks}>
        {items.map((c, i) => (
          <li key={c.id ?? `hidden-${i}`} className={s.check}>
            <Icon
              name={c.status === "hit" ? "check" : c.status === "pending_llm" ? "sparkle" : "circle"}
              className={c.status === "hit" ? "accent" : "muted"}
            />
            <span>
              <span className={s.checkLabel}>{c.label}</span>
              <span className={s.checkMeta}>
                {c.status === "pending_llm"
                  ? "dinilai AI setelah sesi"
                  : c.status === "hit"
                    ? c.hidden
                      ? `tercapai ${at(c.ts)} · detail setelah sesi`
                      : `${c.evidence} · ${c.node} · ${at(c.ts)}`
                    : "belum tercapai"}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Hints({ state, onOpen }: { state: LiveState; onOpen: () => void }) {
  const hints = state.hints ?? [];
  const next = hints.find((h) => !h.opened);
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Hint</h2>
        <span className="panel-meta">memotong skor</span>
      </div>
      {hints.length === 0 && <p className="soft">Soal ini tidak punya hint.</p>}
      <ul className={s.hints}>
        {hints.map((h) =>
          h.opened ? (
            <li key={h.level} className={`${s.hint} ${s.hintOpen}`}>
              <span className={s.hintHead}>
                <Icon name="unlock" size={18} className="accent" />
                Hint level {h.level}
                <span className="gold">−{h.penalty} poin</span>
              </span>
              <p>{h.text}</p>
            </li>
          ) : (
            <li key={h.level}>
              <button
                type="button"
                className={s.hint}
                onClick={onOpen}
                disabled={h !== next}
                title={h === next ? "Buka hint ini" : "Buka hint sebelumnya dulu"}
              >
                <span className={s.hintHead}>
                  <Icon name="lock" size={18} />
                  Hint level {h.level}
                  <span className="gold">−{h.penalty} poin</span>
                </span>
              </button>
            </li>
          ),
        )}
      </ul>
    </section>
  );
}

function Activity({ state }: { state: LiveState }) {
  const items = state.activity ?? [];
  return (
    <section className={`panel ${s.activity}`}>
      <div className="panel-head">
        <h2>Aktivitas</h2>
        <span className="panel-meta">terbaru di atas</span>
      </div>
      {items.length === 0 ? (
        <p className="soft">Belum ada command. Pilih node lalu mulai dari terminal.</p>
      ) : (
        <ul className={s.events}>
          {items.map((e) => (
            <li key={e.id} className={s.event}>
              <span className={e.id.startsWith("H") ? "gold" : "accent"}>{e.id}</span>
              <span className={s.eventNode}>{e.node}</span>
              <span className={`${s.eventCmd} ${e.exit && e.exit !== 0 ? "muted" : ""}`} title={e.command}>
                {e.command}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function HintDialog({ labId, level, penalty, onClose }: { labId: string; level: number; penalty: number; onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = async () => {
    setBusy(true);
    try {
      await api.hint(labId, level);
      onClose();
    } catch (err) {
      setError(String((err as Error).message));
      setBusy(false);
    }
  };
  return (
    <Modal
      title={`Buka hint level ${level}?`}
      onClose={onClose}
      actions={
        <>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Batal
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={open} disabled={busy}>
            Buka · −{penalty} poin
          </button>
        </>
      }
    >
      <p>
        Skor akhir dipotong <strong className="gold">{penalty} poin</strong>. Penalti dihitung sekali per level; membaca
        ulang hint yang sudah dibuka gratis.
      </p>
      <p>Evaluator juga melihat kapan hint dibuka, lalu menilai apa yang kamu lakukan sesudahnya.</p>
      {error && <p className="ember">{error}</p>}
    </Modal>
  );
}

const PHASE: Record<string, string> = {
  verify: "Menjalankan verify.sh…",
  llm: "AI menilai methodology…",
  rules: "Menghitung skor deterministik…",
  archive: "Menyimpan hasil…",
  done: "Selesai",
};

function FinishDialog({
  labId,
  state,
  llmMissing,
  provider,
  onClose,
}: {
  labId: string;
  state: LiveState;
  llmMissing: string[] | null;
  provider: string;
  onClose: () => void;
}) {
  const job = state.job;
  const [error, setError] = useState<string | null>(null);
  const now = useNow(job?.status === "running");
  const llmReady = !llmMissing || llmMissing.length === 0;

  const run = async (useLlm: boolean) => {
    setError(null);
    try {
      await api.evaluate(labId, useLlm);
    } catch (err) {
      setError(String((err as Error).message));
    }
  };

  if (job?.status === "running") {
    return (
      <Modal title="Menilai sesi">
        <p className={s.phase}>
          <span className="dot dot-live" /> {PHASE[job.phase] ?? job.phase}
        </p>
        <p>
          {job.use_llm ? `Provider ${provider}. Biasanya 30–90 detik.` : "Tanpa AI: methodology dan skor akhir dikosongkan."}{" "}
          {clock(now - job.started)}
        </p>
      </Modal>
    );
  }

  return (
    <Modal
      title="Selesai & nilai?"
      onClose={onClose}
      actions={
        <>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Lanjut main
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => run(false)}>
            Nilai tanpa AI
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => run(true)} disabled={!llmReady}>
            Nilai dengan AI
          </button>
        </>
      }
    >
      <p>
        <code>verify.sh</code> memeriksa lab sekarang, lalu evaluator membaca rekaman {state.commands ?? 0} command. Setelah
        dinilai, sesi ini ditutup; terminal tetap bisa dipakai, tapi tidak dinilai lagi.
      </p>
      {!llmReady && (
        <p className="notice notice-ember">
          <span>
            Provider <code>{provider}</code> belum siap: set <code>{llmMissing!.join(", ")}</code> sebelum menjalankan
            server (lihat <code>platform/llm/README.md</code>). Tanpa AI, methodology dan skor akhir belum bisa dihitung.
          </span>
        </p>
      )}
      {(error || job?.status === "error") && (
        <p className="notice notice-ember">
          <span>Penilaian gagal: {error ?? job?.error}</span>
        </p>
      )}
    </Modal>
  );
}
