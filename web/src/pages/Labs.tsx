import { useState } from "react";
import { Link } from "react-router";
import { LabCard, PlannedCard } from "../components/Cards";
import cards from "../components/Cards.module.css";
import { Icon } from "../components/Icon";
import { PageHeader } from "../components/Layout";
import { activeLab, useAppData } from "../lib/appData";
import { COVER, PLANNED_LABS } from "../lib/catalog";
import { category, clock } from "../lib/format";
import { useNow } from "../lib/hooks";
import s from "./Labs.module.css";

const FILTERS = ["Semua", "Networking", "Security", "Problem Solving"] as const;

export function Labs() {
  const { labs, labsError } = useAppData();
  const active = activeLab(labs);
  const now = useNow(Boolean(active?.active_started));
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("Semua");
  const [query, setQuery] = useState("");

  const q = query.trim().toLowerCase();
  const match = (title: string, cat: string | null, extra = "") =>
    (filter === "Semua" || category(cat) === filter) &&
    (!q || `${title} ${category(cat)} ${extra}`.toLowerCase().includes(q));
  const real = (labs ?? []).filter((lab) => match(lab.title, lab.category, `${lab.id} ${lab.summary ?? ""} ${lab.nos ?? ""}`));
  const planned = PLANNED_LABS.filter((lab) => match(lab.title, lab.category));
  const pct = active && active.checkpoints_total ? (active.checkpoints_hit / active.checkpoints_total) * 100 : 0;

  return (
    <>
      <PageHeader title="Labs" />
      <div className={s.toolbar}>
        <div className="tabs" role="group" aria-label="Filter kategori">
          {FILTERS.map((f) => (
            <button key={f} type="button" className="tab" aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {f}
            </button>
          ))}
        </div>
        <label className={s.search}>
          <Icon name="search" size={18} />
          <span className="sr-only">Cari lab</span>
          <input
            type="search"
            placeholder="Cari lab, perangkat, atau topik"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      </div>

      {active && (
        <section className={s.active} aria-label="Sesi yang sedang berjalan">
          <span className={s.activeCover} style={{ background: COVER[category(active.category)] ?? COVER.Networking }} />
          <div className={s.activeBody}>
            <span className="chip chip-accent">Sedang berjalan</span>
            <h2 className={s.activeTitle}>{active.title}</h2>
            <p className="soft">
              {active.id}
              {active.ticket ? ` · tiket ${active.ticket}` : ""} · {active.checkpoints_hit} dari {active.checkpoints_total}{" "}
              checkpoint
              {active.active_started ? ` · ${clock(now - active.active_started)} berjalan` : " · belum ada command"}
            </p>
            <span className="progress-track">
              <span className="progress-fill" style={{ width: `${pct}%`, display: "block" }} />
            </span>
          </div>
          <Link to={`/labs/${active.id}`} className="btn btn-primary">
            Lanjutkan sesi
          </Link>
        </section>
      )}

      <div className={s.sectionHead}>
        <h2 className={s.sectionTitle}>Semua lab</h2>
        <p className="soft">
          {labs?.length ?? 0} lab bisa dimainkan · {PLANNED_LABS.length} segera hadir
        </p>
      </div>
      {labsError && <p className="notice notice-ember">Server tidak bisa dihubungi: {labsError.message}</p>}
      {real.length + planned.length ? (
        <div className={cards.grid4}>
          {real.map((lab) => (
            <LabCard key={lab.id} lab={lab} />
          ))}
          {planned.map((lab) => (
            <PlannedCard key={lab.title} lab={lab} />
          ))}
        </div>
      ) : (
        <p className="empty">Tidak ada lab yang cocok dengan “{query}”.</p>
      )}
    </>
  );
}
