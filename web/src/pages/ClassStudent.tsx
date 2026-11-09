import { Link, useNavigate, useParams } from "react-router";
import { Stat } from "../components/Cards";
import { PageHeader } from "../components/Layout";
import { api } from "../lib/api";
import { band, date, minutes, num } from "../lib/format";
import { useApi } from "../lib/hooks";
import s from "./ClassStudent.module.css";

const rounded = (value: number | null) => (value === null ? "—" : Math.round(value));

export function ClassStudent() {
  const { username = "" } = useParams();
  const { data, error } = useApi(() => api.classStudent(username), [username]);
  const navigate = useNavigate();

  const crumbs = (
    <nav className={s.crumbs} aria-label="Breadcrumb">
      <Link to="/kelas">Progres kelas</Link>
      <span>/</span>
      <span className="soft">{data?.student.display_name ?? username}</span>
    </nav>
  );

  if (error) {
    return (
      <>
        <PageHeader crumbs={crumbs} title="Siswa" />
        <p className="notice notice-ember">{error.message}</p>
      </>
    );
  }
  if (!data) return <PageHeader crumbs={crumbs} title="Memuat…" />;

  const { student } = data;
  const rows = data.sessions;
  const scored = rows.filter((r) => r.final_score !== null).length;

  return (
    <>
      <PageHeader crumbs={crumbs} overline={`@${student.username}`} title={student.display_name} />
      <div className={s.stats}>
        <Stat value={num(data.points)} label="Points · skor akhir terbaik per lab" tone="gold" />
        <Stat value={rows.length} label={`Sesi · ${scored} sudah dinilai`} />
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2>Riwayat sesi</h2>
          <span className="panel-meta">klik baris untuk membuka laporan</span>
        </div>
        {rows.length === 0 ? (
          <p className="empty">Siswa ini belum punya sesi yang dinilai.</p>
        ) : (
          <div className={s.scroll}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th scope="col" className="overline">Lab</th>
                  <th scope="col" className="overline">Tanggal</th>
                  <th scope="col" className="overline">Durasi</th>
                  <th scope="col" className={`overline ${s.num}`}>Command</th>
                  <th scope="col" className={`overline ${s.num}`}>Skor</th>
                  <th scope="col" className="overline">Band</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const href = `/kelas/${student.username}/labs/${r.lab}/sesi/${r.session}`;
                  return (
                    <tr key={`${r.lab}-${r.session}`} onClick={() => navigate(href)}>
                      <td>
                        <Link to={href} className={s.labName}>
                          {r.title}
                        </Link>
                      </td>
                      <td className="soft">{date(r.date)}</td>
                      <td className="soft">{minutes(r.duration_s)}</td>
                      <td className={`${s.num} soft`}>{r.commands}</td>
                      <td className={`${s.num} ${s.score}`}>{rounded(r.final_score)}</td>
                      <td>
                        <span className="chip">{band(r.band)}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
