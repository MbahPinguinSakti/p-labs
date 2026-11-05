import { Link } from "react-router";
import { Avatar, PageHeader } from "../components/Layout";
import { api, type LeaderEntry } from "../lib/api";
import { num } from "../lib/format";
import { useApi } from "../lib/hooks";
import s from "./Leaderboard.module.css";

// P-lab berjalan lokal untuk satu orang, jadi papan ini membandingkan kamu dengan
// golden transcript tiap soal (expert, jalan pintas, trial-and-error, nyontek).
// Leaderboard antar-pengguna menunggu mode multi-user (rencana.md bagian 9).

function meta(e: LeaderEntry) {
  const method = e.methodology_avg === null ? "methodology —" : `methodology ${e.golden ? "" : "rata-rata "}${e.methodology_avg}`;
  return e.golden ? `golden ${e.lab} · ${method}` : `${e.labs} lab · ${method}`;
}

function Name({ e }: { e: LeaderEntry }) {
  const inner = (
    <>
      {e.name}
      {e.you && <span className="soft"> · kamu</span>}
    </>
  );
  return e.golden && e.lab && e.session ? (
    <Link to={`/labs/${e.lab}/sesi/${e.session}`} className={s.name}>
      {inner}
    </Link>
  ) : (
    <span className={s.name}>{inner}</span>
  );
}

export function Leaderboard() {
  const { data, error } = useApi(api.leaderboard, []);
  const entries = data ?? [];
  const top = entries.slice(0, 3);
  const rest = entries.slice(3);
  const you = entries.find((e) => e.you);
  const above = you && you.rank > 1 ? entries[you.rank - 2] : null;

  return (
    <>
      <PageHeader title="Leaderboard" />
      <div className={s.toolbar}>
        <p className="soft">Mode lokal: kamu dibandingkan dengan golden transcript tiap lab.</p>
        <p className="soft">Points = skor akhir sesi, sudah dikurangi penalti hint</p>
      </div>
      {error && <p className="notice notice-ember">{error.message}</p>}

      <div className={s.podium}>
        {top.map((e) => (
          <article key={`${e.rank}-${e.name}`} className={`${s.top} ${e.rank === 1 ? `hero-surface ${s.first}` : ""} ${e.you ? s.you : ""}`}>
            <header className={s.topHead}>
              <Avatar name={e.golden ? "G" : e.name} size={44} />
              <Name e={e} />
              <span className={s.rank}>#{e.rank}</span>
            </header>
            <p className={`${s.points} gold`}>{num(e.points)}</p>
            <p className="soft">{meta(e)}</p>
          </article>
        ))}
      </div>

      {rest.length > 0 && (
        <section className={`panel ${s.list}`}>
          <ol>
            {rest.map((e) => (
              <li key={`${e.rank}-${e.name}`} className={`${s.row} ${e.you ? s.you : ""}`}>
                <span className={s.rowRank}>#{e.rank}</span>
                <Avatar name={e.golden ? "G" : e.name} size={40} />
                <span className={s.rowText}>
                  <Name e={e} />
                  <span className="soft">
                    {meta(e)}
                    {e.you && above ? ` · ${num(Math.max(0, above.points - e.points + 1))} poin lagi ke peringkat #${above.rank}` : ""}
                  </span>
                </span>
                <span className="gold">{num(e.points)}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}
