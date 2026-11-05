import { Link, useParams } from "react-router";
import { Icon } from "../components/Icon";
import { PageHeader } from "../components/Layout";
import { useAppData } from "../lib/appData";
import { useStoredSet } from "../lib/hooks";
import { TRACKS } from "../lib/learn";
import { NotFound } from "./NotFound";
import s from "./Learn.module.css";

export function Learn() {
  const { track = "" } = useParams();
  const data = TRACKS[track];
  const { labs } = useAppData();
  // Modul yang sudah dibaca: kenyamanan per-browser, bukan data penilaian.
  const [done, toggle] = useStoredSet(`p-lab:belajar:${track}`);
  if (!data) return <NotFound />;

  const labByTitle = new Map((labs ?? []).map((lab) => [lab.title, lab]));
  const current = data.modules.findIndex((m) => !done.has(m.title));
  const linked = new Set(data.modules.map((m) => m.lab).filter(Boolean)).size;
  const pct = (data.modules.filter((m) => done.has(m.title)).length / data.modules.length) * 100;

  return (
    <>
      <PageHeader overline="Belajar" title={data.title} />
      <section className={`panel ${s.intro}`}>
        <div className={s.introText}>
          <p>{data.intro}</p>
          <p className="soft">
            {data.modules.length} modul · {done.size} selesai · {data.scope === "lab terkait" ? `${linked} lab terkait` : data.scope}
          </p>
          <span className="progress-track">
            <span className="progress-fill" style={{ width: `${pct}%`, display: "block" }} />
          </span>
        </div>
        {current >= 0 && (
          <a href={`#modul-${current + 1}`} className="btn btn-primary">
            {done.size ? "Lanjutkan" : "Mulai"}: {data.modules[current].title}
          </a>
        )}
      </section>

      <div className={s.columns}>
        <ol className={s.modules}>
          {data.modules.map((m, i) => {
            const isDone = done.has(m.title);
            const lab = m.lab ? labByTitle.get(m.lab) : undefined;
            return (
              <li key={m.title} id={`modul-${i + 1}`} className={`${s.module} ${i === current ? s.current : ""}`}>
                <button
                  type="button"
                  className={`${s.mark} ${isDone ? s.markDone : ""}`}
                  onClick={() => toggle(m.title)}
                  aria-pressed={isDone}
                  title={isDone ? "Tandai belum dibaca" : "Tandai sudah dibaca"}
                >
                  {isDone ? <Icon name="check" size={18} /> : i + 1}
                </button>
                <div className={s.moduleText}>
                  <h2>{m.title}</h2>
                  <p>{m.body}</p>
                  <p className={s.meta}>
                    {m.lab ? (
                      lab ? (
                        <Link to={`/labs/${lab.id}`} className="accent">
                          {track === "problem-solving" ? "Contoh" : "Lab"}: {m.lab}
                        </Link>
                      ) : (
                        <span>Lab: {m.lab} (segera hadir)</span>
                      )
                    ) : (
                      m.note && <span>{m.note}</span>
                    )}
                    {(m.lab || m.note) && " · "}±{m.read} menit baca
                  </p>
                </div>
              </li>
            );
          })}
        </ol>

        <aside className={s.side}>
          {data.side.map((block) => (
            <section key={block.title} className="panel">
              <h2 className={s.sideTitle}>{block.title}</h2>
              {block.subtitle && <p className={s.sideSub}>{block.subtitle}</p>}
              <dl className={s.items}>
                {block.items.map((item) => (
                  <div key={item.term} className={item.code ? s.codeItem : undefined}>
                    <dt>{item.code ? <code className="accent">{item.term}</code> : item.term}</dt>
                    <dd>{item.desc}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </aside>
      </div>
    </>
  );
}
