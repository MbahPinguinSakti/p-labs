import { NavLink, Outlet } from "react-router";
import { activeLab, useAppData } from "../lib/appData";
import { clock } from "../lib/format";
import { useNow } from "../lib/hooks";
import { Icon } from "./Icon";
import s from "./Layout.module.css";

const MAIN = [
  { to: "/", label: "Home", icon: "home", end: true },
  { to: "/progress", label: "Progress", icon: "chart" },
  { to: "/labs", label: "Labs", icon: "flask" },
  { to: "/leaderboard", label: "Leaderboard", icon: "trophy" },
];
const LEARN = [
  { to: "/belajar/networking", label: "Networking", icon: "network" },
];

function NavItem({ to, label, icon, end }: { to: string; label: string; icon: string; end?: boolean }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => `${s.navItem} ${isActive ? s.navActive : ""}`}>
      <Icon name={icon} />
      <span>{label}</span>
    </NavLink>
  );
}

function ActiveSession() {
  const { labs } = useAppData();
  const lab = activeLab(labs);
  const now = useNow(Boolean(lab?.active_started));
  if (!lab) {
    return <p className={s.noSession}>Belum ada sesi berjalan.</p>;
  }
  const pct = lab.checkpoints_total ? (lab.checkpoints_hit / lab.checkpoints_total) * 100 : 0;
  return (
    <NavLink to={`/labs/${lab.id}`} className={({ isActive }) => `${s.session} ${isActive ? s.sessionActive : ""}`}>
      <span className={s.sessionStatus}>
        <span className="dot dot-live" /> Sedang berjalan
      </span>
      <span className={s.sessionTitle}>{lab.title}</span>
      <span className={s.sessionMeta}>
        {lab.id} · {lab.checkpoints_hit}/{lab.checkpoints_total}
        {lab.active_started ? ` · ${clock(now - lab.active_started)}` : " · belum mulai"}
      </span>
      <span className="progress-track">
        <span className="progress-fill" style={{ width: `${pct}%`, display: "block" }} />
      </span>
    </NavLink>
  );
}

export function Layout() {
  return (
    <div className={s.shell}>
      <aside className={s.sidebar}>
        <NavLink to="/" className={s.brand} aria-label="P-lab, ke Home">
          <span className={s.brandMark} aria-hidden="true">
            P
          </span>
          <span className={s.brandText}>P-lab</span>
        </NavLink>
        <nav aria-label="Utama" className={s.nav}>
          {MAIN.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </nav>
        <p className={`overline ${s.section}`}>Belajar</p>
        <nav aria-label="Belajar" className={s.nav}>
          {LEARN.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </nav>
        <p className={`overline ${s.section}`}>Sesi aktif</p>
        <ActiveSession />
      </aside>
      <main className={s.main} id="konten">
        <Outlet />
      </main>
    </div>
  );
}

/** Judul halaman + chip akun di kanan atas (pola semua halaman di desain). */
export function PageHeader({
  title,
  overline,
  crumbs,
  actions,
}: {
  title: string;
  overline?: React.ReactNode;
  crumbs?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className={s.header}>
      <div className={s.headerText}>
        {crumbs}
        {overline && <p className="overline">{overline}</p>}
        <h1 className={s.title}>{title}</h1>
      </div>
      <div className={s.headerActions}>{actions ?? <Account />}</div>
    </header>
  );
}

export function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  return (
    <span className={s.avatar} style={{ width: size, height: size, fontSize: size * 0.38 }} aria-hidden="true">
      {name.slice(0, 1).toUpperCase()}
    </span>
  );
}

const ROLE_LABEL = { admin: "Admin", guru: "Guru", siswa: "Siswa" } as const;

/** Chip akun. Mode server: nama + role dan tombol Keluar; pribadi: akun lokal saja. */
export function Account() {
  const { me, logout } = useAppData();
  const name = me?.user?.display_name ?? "…";
  if (!me?.auth) {
    return (
      <span className={s.account} title="Akun lokal (env LAB_USER)">
        <Avatar name={name} size={32} />
        <span>{name}</span>
      </span>
    );
  }
  return (
    <span className={s.accountGroup}>
      <span className={s.account} title={me.user ? `Login sebagai ${me.user.username}` : undefined}>
        <Avatar name={name} size={32} />
        <span className={s.accountText}>
          <span>{name}</span>
          {me.user && <span className={s.accountRole}>{ROLE_LABEL[me.user.role] ?? me.user.role}</span>}
        </span>
      </span>
      <button type="button" className="btn btn-secondary btn-sm" onClick={() => void logout()}>
        Keluar
      </button>
    </span>
  );
}
