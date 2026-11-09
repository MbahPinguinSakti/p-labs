import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { PageHeader } from "../components/Layout";
import { api, CLASS_EXPORT_URL, type ClassStudent } from "../lib/api";
import { date, num } from "../lib/format";
import { useApi } from "../lib/hooks";
import s from "./ClassProgress.module.css";

type SortKey = "points" | "name";

// Poin: tertinggi dulu (seri: nama). Nama: abjad.
function sortStudents(students: ClassStudent[], key: SortKey) {
  const byName = (a: ClassStudent, b: ClassStudent) => a.display_name.localeCompare(b.display_name, "id");
  return [...students].sort((a, b) => (key === "points" ? b.points - a.points || byName(a, b) : byName(a, b)));
}

export function ClassProgress() {
  const { data, error } = useApi(api.classProgress, []);
  const [sort, setSort] = useState<SortKey>("points");
  const navigate = useNavigate();

  if (error) {
    return (
      <>
        <PageHeader title="Progres kelas" />
        <p className="notice notice-ember">{error.message}</p>
      </>
    );
  }
  if (!data) return <PageHeader title="Progres kelas" />;

  const students = sortStudents(data.students, sort);
  const ariaSort = (key: SortKey) => (sort === key ? (key === "points" ? "descending" : "ascending") : "none");

  return (
    <>
      <PageHeader title="Progres kelas" />
      <div className={s.toolbar}>
        <p className="soft">{students.length} siswa · skor terbaik per lab, dibulatkan</p>
        <a className="btn btn-secondary btn-sm" href={CLASS_EXPORT_URL} download>
          Export CSV
        </a>
      </div>

      {students.length === 0 ? (
        <p className="empty">Belum ada siswa.</p>
      ) : (
        <section className="panel">
          <div className={s.scroll}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th scope="col" className="overline" aria-sort={ariaSort("name")}>
                    <button type="button" className={s.sortBtn} onClick={() => setSort("name")}>
                      Nama{sort === "name" ? " ↑" : ""}
                    </button>
                  </th>
                  <th scope="col" className={`overline ${s.num}`} aria-sort={ariaSort("points")}>
                    <button type="button" className={s.sortBtn} onClick={() => setSort("points")}>
                      Poin{sort === "points" ? " ↓" : ""}
                    </button>
                  </th>
                  <th scope="col" className={`overline ${s.num}`}>
                    Sesi
                  </th>
                  <th scope="col" className="overline">
                    Sesi terakhir
                  </th>
                  {data.labs.map((lab) => (
                    <th scope="col" key={lab.id} className={`overline ${s.labHead}`}>
                      {lab.title}
                      <span className={s.labId}>{lab.id}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {students.map((st) => (
                  <tr key={st.username} onClick={() => navigate(`/kelas/${st.username}`)}>
                    <th scope="row" className={s.nameCell}>
                      <Link to={`/kelas/${st.username}`} className={s.name}>
                        {st.display_name}
                      </Link>
                      <span className={s.user}>{st.username}</span>
                    </th>
                    <td className={`${s.num} gold`}>{num(st.points)}</td>
                    <td className={`${s.num} soft`}>{st.sessions}</td>
                    <td className="soft">{date(st.last_session)}</td>
                    {data.labs.map((lab) => {
                      const best = st.best_scores[lab.id] as number | undefined;
                      const attempts = st.attempts[lab.id] ?? 0;
                      return (
                        <td key={lab.id} className={s.num}>
                          {best === undefined ? (
                            <span className="muted">–</span>
                          ) : (
                            <>
                              <span className={s.best}>{Math.round(best)}</span>{" "}
                              <span className={s.attempts}>· {attempts} percobaan</span>
                            </>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
