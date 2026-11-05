import { useState } from "react";
import { Link } from "react-router";
import { LabCard, PlannedCard, Stat } from "../components/Cards";
import cards from "../components/Cards.module.css";
import { Icon } from "../components/Icon";
import { Avatar, PageHeader } from "../components/Layout";
import { Topology } from "../components/Topology";
import { api } from "../lib/api";
import { activeLab, useAppData } from "../lib/appData";
import { PLANNED_LABS } from "../lib/catalog";
import { category, difficulty, num } from "../lib/format";
import { useApi } from "../lib/hooks";
import s from "./Home.module.css";

const FILTERS = ["Semua", "Networking", "Security"] as const;

export function Home() {
  const { me, labs } = useAppData();
  const featured = labs?.[0] ?? null;
  const active = activeLab(labs);
  const detail = useApi(() => (featured ? api.lab(featured.id) : Promise.resolve(null)), [featured?.id]);
  const progress = useApi(api.progress, []);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("Semua");

  const sessions = progress.data?.sessions ?? [];
  const labsDone = new Set(sessions.filter((r) => r.final_score !== null).map((r) => r.lab)).size;
  const match = (cat: string | null) => filter === "Semua" || category(cat) === filter;
  const realLabs = (labs ?? []).filter((lab) => match(lab.category));
  const planned = PLANNED_LABS.filter((lab) => match(lab.category));
  const shown = [...realLabs.map((lab) => ({ real: lab })), ...planned.map((lab) => ({ planned: lab }))].slice(0, 4);

  const actions = [
    { to: featured ? `/labs/${featured.id}` : "/labs", icon: "play", label: "Mulai Lab" },
    { to: active ? `/labs/${active.id}` : null, icon: "terminal", label: "Lanjutkan" },
    { to: "/belajar/networking", icon: "bulb", label: "Materi" },
    { to: "/leaderboard", icon: "trophy", label: "Leaderboard" },
  ];

  return (
    <>
      <PageHeader title="Home" />

      <div className={s.toolbar}>
        <nav className={s.quick} aria-label="Aksi cepat">
          {actions.map((a) =>
            a.to ? (
              <Link key={a.label} to={a.to} className={s.quickItem}>
                <span className={s.quickIcon}>
                  <Icon name={a.icon} size={22} />
                </span>
                {a.label}
              </Link>
            ) : (
              <span key={a.label} className={`${s.quickItem} ${s.quickOff}`} title="Belum ada sesi berjalan">
                <span className={s.quickIcon}>
                  <Icon name={a.icon} size={22} />
                </span>
                {a.label}
              </span>
            ),
          )}
        </nav>
      </div>

      {featured && (
        <section className={`hero-surface ${s.hero}`} aria-labelledby="featured-title">
          <div className={s.heroText}>
            <p className={s.heroMeta}>
              <span className="chip chip-accent">{active?.id === featured.id ? "Sedang berjalan" : "Lab unggulan"}</span>
              <span className="soft">
                {category(featured.category)} · {difficulty(featured.difficulty)}
              </span>
            </p>
            <h2 id="featured-title" className={s.heroTitle}>
              {featured.title}
            </h2>
            {featured.summary && <p className={s.heroLead}>{featured.summary}</p>}
            <Link to={`/labs/${featured.id}`} className="btn btn-primary">
              {active?.id === featured.id
                ? "Lanjutkan sesi"
                : `Mulai lab${featured.duration_min ? ` · ±${featured.duration_min} menit` : ""}`}
            </Link>
          </div>
          {detail.data && (
            <div className={s.heroVisual} aria-label="Topologi lab">
              <Topology
                nodes={detail.data.topology.nodes}
                links={detail.data.topology.links}
                orientation="horizontal"
                pitch={96}
                showLabels={false}
              />
            </div>
          )}
        </section>
      )}

      <div className={s.stats}>
        <Stat value={me?.user ?? "…"} label="Akun lokal">
          <Avatar name={me?.user ?? "?"} size={44} />
        </Stat>
        <Stat value={num(progress.data?.points ?? 0)} label="Points" tone="gold" />
        <Stat value={labsDone} label={`Lab selesai · dari ${labs?.length ?? 0} lab tersedia`} />
      </div>

      <section aria-labelledby="labs-title">
        <div className={s.sectionHead}>
          <div>
            <h2 id="labs-title" className={s.sectionTitle}>
              Lab
            </h2>
            <p className="soft">Yang sudah bisa dimainkan, lalu yang segera hadir</p>
          </div>
          <div className={s.sectionSide}>
            <div className="tabs" role="group" aria-label="Filter kategori">
              {FILTERS.map((f) => (
                <button key={f} type="button" className="tab" aria-pressed={filter === f} onClick={() => setFilter(f)}>
                  {f}
                </button>
              ))}
            </div>
            <Link to="/labs" className="accent">
              Lihat semua lab
            </Link>
          </div>
        </div>
        {shown.length ? (
          <div className={cards.grid4}>
            {shown.map((item) =>
              "real" in item ? (
                <LabCard key={item.real.id} lab={item.real} />
              ) : (
                <PlannedCard key={item.planned.title} lab={item.planned} />
              ),
            )}
          </div>
        ) : (
          <p className="empty">Belum ada lab di kategori ini.</p>
        )}
      </section>
    </>
  );
}
