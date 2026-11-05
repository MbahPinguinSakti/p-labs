import { Link } from "react-router";
import type { LabCard as Lab } from "../lib/api";
import { COVER, type PlannedLab } from "../lib/catalog";
import { category, difficulty, score } from "../lib/format";
import s from "./Cards.module.css";

function Cover({ cat, level }: { cat: string; level: string | null }) {
  return (
    <span className={s.cover} style={{ background: COVER[cat] ?? COVER.Networking }}>
      {level && <span className={s.level}>{level}</span>}
    </span>
  );
}

function labStatus(lab: Lab) {
  if (lab.active_session) {
    return <span className="accent">Sedang berjalan · {lab.checkpoints_hit}/{lab.checkpoints_total} checkpoint</span>;
  }
  if (lab.best_score !== null) {
    return <span className="accent">Selesai · skor terbaik {score(lab.best_score)}</span>;
  }
  return <span>Belum dimulai</span>;
}

export function LabCard({ lab }: { lab: Lab }) {
  const cat = category(lab.category);
  return (
    <Link to={`/labs/${lab.id}`} className={s.card}>
      <Cover cat={cat} level={difficulty(lab.difficulty)} />
      <span className={s.body}>
        <span className={s.title}>{lab.title}</span>
        <span className={s.meta}>
          {cat}
          {lab.duration_min ? ` · ±${lab.duration_min} menit` : ""}
        </span>
        <span className={s.status}>{labStatus(lab)}</span>
      </span>
    </Link>
  );
}

export function PlannedCard({ lab }: { lab: PlannedLab }) {
  const cat = category(lab.category);
  return (
    <div className={`${s.card} ${s.planned}`} aria-disabled="true">
      <Cover cat={cat} level={difficulty(lab.difficulty)} />
      <span className={s.body}>
        <span className={s.title}>{lab.title}</span>
        <span className={s.meta}>
          {cat} · ±{lab.duration_min} menit
        </span>
        <span className={`${s.status} muted`}>Segera hadir</span>
      </span>
    </div>
  );
}

export function Stat({
  value,
  label,
  tone,
  children,
}: {
  value: React.ReactNode;
  label: React.ReactNode;
  tone?: "gold" | "accent";
  children?: React.ReactNode;
}) {
  return (
    <div className={s.stat}>
      {children}
      <span className={s.statText}>
        <span className={`${s.statValue} ${tone ?? ""}`}>{value}</span>
        <span className={s.statLabel}>{label}</span>
      </span>
    </div>
  );
}
