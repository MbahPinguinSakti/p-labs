import { useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { Icon } from "../components/Icon";
import { PageHeader } from "../components/Layout";
import { api, type Evaluation, type TimelineEntry } from "../lib/api";
import { band, clock, date, DIMENSION_LABEL, DIMENSIONS, minutes, score } from "../lib/format";
import { useApi } from "../lib/hooks";
import s from "./Result.module.css";

export function Result() {
  // Rute guru (/kelas/:username/...) memakai endpoint kelas; rute siswa tetap seperti semula.
  const { labId = "", session = "", username } = useParams();
  const { data, error } = useApi(
    () => (username ? api.classSession(username, labId, session) : api.result(labId, session)),
    [labId, session, username],
  );
  const [showTimeline, setShowTimeline] = useState(false);
  const timelineRef = useRef<HTMLElement>(null);

  if (error) {
    return (
      <>
        <PageHeader title="Hasil evaluasi" />
        <p className="notice notice-ember">{error.message}</p>
      </>
    );
  }
  if (!data) return <PageHeader title="Memuat hasil…" />;

  const r = data.result;
  const byId = new Map(data.timeline.map((e) => [e.id, e]));
  const openTimeline = () => {
    setShowTimeline(true);
    requestAnimationFrame(() => timelineRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  return (
    <>
      <PageHeader
        crumbs={
          username ? (
            <nav className={s.crumbs} aria-label="Breadcrumb">
              <Link to="/kelas">Progres kelas</Link>
              <span>/</span>
              <Link to={`/kelas/${username}`}>{username}</Link>
              <span>/</span>
              <span className="soft">{data.title}</span>
            </nav>
          ) : (
            <nav className={s.crumbs} aria-label="Breadcrumb">
              <Link to="/labs">Labs</Link>
              <span>/</span>
              <Link to={`/labs/${labId}`}>{data.title}</Link>
              <span>/</span>
              <span className="soft">{data.kind === "golden" ? `Golden ${session}` : `Sesi ${date(data.date)}`}</span>
            </nav>
          )
        }
        title="Hasil evaluasi"
      />

      <section className={`hero-surface ${s.hero}`}>
        <div className={s.heroText}>
          <p className={s.chips}>
            <span className="chip chip-accent">Methodology · {band(r.llm?.methodology.band)}</span>
            <span className="chip">
              {r.problem} · sesi {r.session}
            </span>
            {data.kind === "golden" && <span className="chip chip-gold">golden transcript</span>}
          </p>
          <h2 className={s.heroTitle}>{data.title}</h2>
          {data.label && <p className="soft">{data.label}</p>}
          <p className={s.summary}>
            {r.llm?.feedback.summary ??
              "Sesi ini dinilai tanpa AI: correctness, efficiency, dan safety sudah dihitung, tapi methodology dan skor akhir butuh evaluator LLM."}
          </p>
        </div>
        <div className={s.heroScore}>
          <p className="overline">Skor akhir</p>
          <p className={s.final}>
            {score(r.final_score)}
            <span> / 100</span>
          </p>
          <p className="soft">
            {minutes(data.duration_s)} · {data.timeline.filter((e) => e.id.startsWith("E")).length} command
          </p>
          <div className={s.heroActions}>
            <button type="button" className="btn btn-secondary" onClick={openTimeline}>
              Lihat timeline
            </button>
            {username ? (
              <Link to={`/kelas/${username}`} className="btn btn-primary">
                Kembali ke siswa
              </Link>
            ) : (
              <Link to={`/labs/${labId}`} className="btn btn-primary">
                Coba lagi
              </Link>
            )}
          </div>
        </div>
      </section>

      <div className={s.dims}>
        {DIMENSIONS.map((d) => {
          const raw = r.scores[d];
          const credited = r.credited[d];
          return (
            <div key={d} className={s.dim}>
              <span className={s.dimValue}>{raw ?? "—"}</span>
              <span className="soft">
                {DIMENSION_LABEL[d]} · bobot {Math.round((r.weights[d] ?? 0) * 100)}%
              </span>
              {raw !== null && credited !== null && credited !== raw && (
                <span className="ember">dikreditkan {score(credited)} (process gate)</span>
              )}
            </div>
          );
        })}
      </div>
      <Explain r={r} />

      <div className={s.columns}>
        <div className={s.left}>
          <KeyMoments r={r} byId={byId} total={data.timeline.length} />
          <Checkpoints r={r} labels={data.checkpoint_labels} />
        </div>
        <Feedback r={r} />
      </div>

      {showTimeline && <Timeline ref={timelineRef} timeline={data.timeline} r={r} />}
    </>
  );
}

function Explain({ r }: { r: Evaluation }) {
  const gate = r.rule_based.process_gate;
  const eff = r.rule_based.efficiency;
  const verify = r.rule_based.verify;
  const parts: string[] = [];
  if (gate?.waived) {
    parts.push(`Process gate tidak diterapkan: ${gate.waived}; diagnosis di Winbox tidak terekam`);
  } else if (gate) {
    parts.push(
      gate.factor === 1
        ? `Process gate ×1.0: diagnosis terjadi sebelum fix, jadi ${gate.applies_to.join(" dan ")} dihitung penuh`
        : `Process gate ×${gate.factor}: ${gate.missing.join(", ")} belum terjadi sebelum ${gate.before}, jadi ${gate.applies_to.join(" dan ")} dipotong`,
    );
  }
  parts.push(`efficiency ${eff.score}: ${eff.state_changes} perubahan state (baseline ${eff.baseline_changes})`);
  if (verify.issues?.length) parts.push(`correctness ${verify.correctness}: ${verify.issues.join("; ")}`);
  if (r.rule_based.hints.penalty) {
    parts.push(`hint level ${r.rule_based.hints.levels_used.join(", ")}: −${r.rule_based.hints.penalty} poin dari skor akhir`);
  }
  return (
    <p className={s.explain}>
      <Icon name={gate && gate.factor < 1 ? "alert" : "check"} size={18} className={gate && gate.factor < 1 ? "ember" : "accent"} />
      <span>{parts.join(" · ")}</span>
    </p>
  );
}

function badEvents(r: Evaluation, timeline?: Map<string, TimelineEntry>) {
  const bad = new Set<string>();
  for (const v of r.rule_based.safety.violations) for (const e of v.events ?? []) bad.add(e);
  if (timeline) for (const [id, e] of timeline) if (e.rework.length) bad.add(id);
  return bad;
}

function KeyMoments({ r, byId, total }: { r: Evaluation; byId: Map<string, TimelineEntry>; total: number }) {
  const moments = r.llm?.feedback.key_moments ?? [];
  const bad = badEvents(r, byId);
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Momen kunci</h2>
        <span className="panel-meta">
          {moments.length} dari {total} event
        </span>
      </div>
      {moments.length === 0 ? (
        <p className="soft">Momen kunci ditulis evaluator AI. Sesi ini dinilai tanpa AI.</p>
      ) : (
        <ul className={s.moments}>
          {moments.map((m) => {
            const e = byId.get(m.event);
            return (
              <li key={m.event} className={s.moment}>
                <span className={`chip ${bad.has(m.event) ? "chip-ember" : "chip-accent"} ${s.eventChip}`}>{m.event}</span>
                <span>
                  {e && (
                    <code className={s.momentCmd}>
                      {e.node} · {e.command}
                    </code>
                  )}
                  <p className={s.momentNote}>{m.note}</p>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Checkpoints({ r, labels }: { r: Evaluation; labels: Record<string, string> }) {
  const rows = [
    ...r.rule_based.checkpoints.map((c) => ({ id: c.id, hit: c.hit, meta: c.hit ? `${c.event}` : "tidak tercapai" })),
    ...(r.llm?.llm_checkpoints ?? []).map((c) => ({ id: c.id, hit: c.hit, meta: "dinilai AI", rationale: c.rationale })),
  ] as { id: string; hit: boolean; meta: string; rationale?: string }[];
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Checkpoint</h2>
        <span className="panel-meta">
          {rows.filter((c) => c.hit).length} dari {rows.length}
        </span>
      </div>
      <ul className={s.checks}>
        {rows.map((c) => (
          <li key={c.id} className={s.check} title={c.rationale}>
            <Icon name={c.hit ? "check" : "x"} size={18} className={c.hit ? "accent" : "ember"} />
            <span>{labels[c.id] ?? c.id}</span>
            <span className="soft">{c.meta}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Feedback({ r }: { r: Evaluation }) {
  const f = r.llm?.feedback;
  const violations = r.rule_based.safety.violations;
  return (
    <section className={`panel ${s.feedback}`}>
      <div className="panel-head">
        <h2>Feedback</h2>
      </div>
      {f ? (
        <>
          <Group title="Yang sudah bagus" items={f.strengths} />
          <Group title="Perlu diperbaiki" items={f.improvements} />
          <Group title="Pelajaran teknis" items={f.technical_lessons} />
          <Group title="Latihan berikutnya" items={[f.next_practice]} />
        </>
      ) : (
        <p className="soft">Feedback naratif ditulis evaluator AI. Nilai ulang dengan AI untuk melihatnya.</p>
      )}
      <p className="overline">Pelanggaran safety</p>
      {violations.length ? (
        <ul className={s.violations}>
          {violations.map((v) => (
            <li key={v.id} className="chip chip-ember" title={`${v.reason}${v.events ? ` (${v.events.join(", ")})` : ""}`}>
              {v.id} · {v.severity}
            </li>
          ))}
        </ul>
      ) : (
        <p className="accent">Tidak ada.</p>
      )}
      {r.warnings.length > 0 && <p className="muted">Peringatan evaluator: {r.warnings.join("; ")}</p>}
    </section>
  );
}

function Group({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className={s.group}>
      <p className="overline">{title}</p>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function Timeline({ timeline, r, ref }: { timeline: TimelineEntry[]; r: Evaluation; ref: React.Ref<HTMLElement> }) {
  const bad = badEvents(r);
  return (
    <section ref={ref} className={`panel ${s.timeline}`} aria-labelledby="timeline-title">
      <div className="panel-head">
        <h2 id="timeline-title">Timeline</h2>
        <span className="panel-meta">{timeline.length} event · klik baris untuk melihat output</span>
      </div>
      <ol className={s.rows}>
        {timeline.map((e) => (
          <li key={e.id}>
            <details className={s.row}>
              <summary>
                <span className={e.hint_level ? "gold" : bad.has(e.id) ? "ember" : "accent"}>{e.id}</span>
                <span className="muted">+{clock(e.t)}</span>
                <span>{e.node}</span>
                <code className={e.exit ? "muted" : undefined}>{e.command}</code>
                <span className={s.flags}>
                  {e.source && <span className="chip chip-gold">{e.source}</span>}
                  {e.state_change.length > 0 && <span className="chip">ubah state</span>}
                  {e.rework.length > 0 && <span className="chip chip-ember">rework</span>}
                  {e.exit !== null && e.exit !== 0 && <span className="chip">exit {e.exit}</span>}
                </span>
              </summary>
              <pre className={s.output}>
                {e.output || (e.source ? `(perubahan dari ${e.source}, direkam dari konfigurasi router)` : "(tidak ada output terekam)")}
              </pre>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}

