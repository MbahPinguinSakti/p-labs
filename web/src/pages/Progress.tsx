import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Stat } from "../components/Cards";
import { Icon } from "../components/Icon";
import { PageHeader } from "../components/Layout";
import { api, type ProgressData } from "../lib/api";
import { band, date, DIMENSION_LABEL, DIMENSIONS, minutes, num, score } from "../lib/format";
import { useApi } from "../lib/hooks";
import s from "./Progress.module.css";

type Row = ProgressData["sessions"][number];

const mean = (values: number[]) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null);

export function Progress() {
  const { data, error } = useApi(api.progress, []);
  const navigate = useNavigate();
  if (error) {
    return (
      <>
        <PageHeader title="Progress" />
        <p className="notice notice-ember">{error.message}</p>
      </>
    );
  }
  const rows = data?.sessions ?? [];
  const scored = rows.filter((r) => r.scores);
  const week = Date.now() / 1000 - 7 * 86400;
  const labsDone = new Set(rows.filter((r) => r.final_score !== null).map((r) => r.lab));
  const methodology = scored.map((r) => r.scores!.methodology).filter((v): v is number => v !== null);
  const avgMethod = mean(methodology);

  return (
    <>
      <PageHeader title="Progress" />
      <div className={s.stats}>
        <Stat value={num(data?.points ?? 0)} label="Points · skor akhir terbaik per lab" tone="gold" />
        <Stat
          value={labsDone.size}
          label={`Lab selesai · ${rows.filter((r) => (r.date ?? 0) > week).length} sesi dalam 7 hari terakhir`}
        />
        <Stat value={avgMethod === null ? "—" : Math.round(avgMethod)} label={`Rata-rata methodology · ${methodology.length} sesi`} />
      </div>

      {rows.length === 0 ? (
        <div className="empty">
          Belum ada sesi yang dinilai. Mainkan lab sampai <strong>Selesai &amp; nilai</strong>, lalu riwayatnya muncul di
          sini. <Link to="/labs" className="accent">Buka Labs</Link>
        </div>
      ) : (
        <>
          <div className={s.charts}>
            <MethodologyChart rows={rows} />
            <section className="panel">
              <div className="panel-head">
                <h2>Rata-rata per dimensi</h2>
                <span className="panel-meta">{scored.length} sesi</span>
              </div>
              <ul className={s.meters}>
                {DIMENSIONS.map((d) => {
                  const avg = mean(scored.map((r) => r.scores![d]).filter((v): v is number => v !== null));
                  return (
                    <li key={d}>
                      <span className={s.meterHead}>
                        <span>{DIMENSION_LABEL[d]}</span>
                        <span>{avg === null ? "—" : Math.round(avg)}</span>
                      </span>
                      <span className="progress-track" role="meter" aria-valuenow={avg ?? 0} aria-valuemin={0} aria-valuemax={100} aria-label={DIMENSION_LABEL[d]}>
                        <span className="progress-fill" style={{ width: `${avg ?? 0}%`, display: "block" }} />
                      </span>
                    </li>
                  );
                })}
              </ul>
            </section>
          </div>

          <section className="panel">
            <div className="panel-head">
              <h2>Riwayat sesi</h2>
              <span className="panel-meta">klik baris untuk membuka hasil evaluasi</span>
            </div>
            <table className={s.table}>
              <thead>
                <tr>
                  <th className="overline">Lab</th>
                  <th className="overline">Tanggal</th>
                  <th className="overline">Durasi</th>
                  <th className="overline">Band</th>
                  <th className="overline">Skor</th>
                  <th aria-label="Buka" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.lab}-${r.session}`} onClick={() => navigate(`/labs/${r.lab}/sesi/${r.session}`)}>
                    <td>
                      <Link to={`/labs/${r.lab}/sesi/${r.session}`} className={s.labName}>
                        {r.title}
                      </Link>
                    </td>
                    <td className="soft">{date(r.date)}</td>
                    <td className="soft">{minutes(r.duration_s)}</td>
                    <td>
                      <span className="chip">{band(r.band)}</span>
                    </td>
                    <td className="soft">{score(r.final_score)}</td>
                    <td>
                      <Icon name="arrow" size={18} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </>
  );
}

function MethodologyChart({ rows }: { rows: Row[] }) {
  // 8 sesi terakhir, urut waktu. Satu seri: tanpa legend, judul panel menamainya.
  const series = rows
    .filter((r) => r.scores?.methodology !== null && r.scores?.methodology !== undefined)
    .slice(0, 8)
    .reverse();
  const [hover, setHover] = useState<number | null>(null);
  const last = series.length - 1;
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Methodology per sesi</h2>
        <span className="panel-meta">{series.length} sesi terakhir</span>
      </div>
      {series.length === 0 ? (
        <p className="soft">Belum ada sesi yang dinilai dengan AI.</p>
      ) : (
        <>
          <div className={s.chart} role="img" aria-label={`Skor methodology: ${series.map((r) => r.scores!.methodology).join(", ")}`}>
            {series.map((r, i) => {
              const value = r.scores!.methodology!;
              return (
                <div
                  key={r.session}
                  className={s.barSlot}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                >
                  {(i === last || hover === i) && (
                    <span className={s.barLabel} style={{ bottom: `calc(${value}% + 8px)` }}>
                      {hover === i ? `${value} · ${r.title}` : value}
                    </span>
                  )}
                  <span className={`${s.bar} ${i === last ? s.barLast : ""}`} style={{ height: `${Math.max(value, 1)}%` }} />
                </div>
              );
            })}
          </div>
          <div className={s.axis}>
            {series.map((r) => (
              <span key={r.session}>{date(r.date, false)}</span>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
