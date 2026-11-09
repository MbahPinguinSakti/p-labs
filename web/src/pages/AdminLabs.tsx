import { useCallback, useState } from "react";
import { PageHeader } from "../components/Layout";
import { Modal } from "../components/Modal";
import { api, type AdminLab, type AdminLabs as AdminLabsData } from "../lib/api";
import { num } from "../lib/format";
import { useApi } from "../lib/hooks";
import s from "./AdminLabs.module.css";

const REFRESH_MS = 10_000;

const STEP: Record<string, string> = {
  destroy: "membersihkan",
  deploy: "menyalakan node",
  verify: "memverifikasi",
  inject: "menyuntikkan konfigurasi",
  done: "selesai",
};

const BUSY_REASON = { deploy: "Sedang di-deploy", evaluate: "Sedang dinilai", stop: "Sedang dimatikan" } as const;

function idleText(seconds: number | null) {
  if (seconds === null) return "—";
  if (seconds < 60) return "baru saja";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} menit lalu`;
  return `${Math.floor(seconds / 3600)} jam lalu`;
}

function Status({ lab }: { lab: AdminLab }) {
  if (lab.state === "deploying") {
    const step = lab.deploy_step ? (STEP[lab.deploy_step] ?? lab.deploy_step) : null;
    return (
      <span className="chip chip-gold">
        <span className={`dot dot-live ${s.dotGold}`} aria-hidden="true" />
        deploy{step ? ` · ${step}` : ""}
      </span>
    );
  }
  if (lab.state === "running") {
    return (
      <span className="chip chip-accent">
        <span className="dot" aria-hidden="true" />
        berjalan
      </span>
    );
  }
  return <span className="chip">berhenti</span>;
}

function Capacity({ c }: { c: AdminLabsData["capacity"] }) {
  const pct = c.limit_mb > 0 ? Math.min(100, (c.used_mb / c.limit_mb) * 100) : 0;
  return (
    <section className="panel" aria-labelledby="kapasitas-judul">
      <div className="panel-head">
        <h2 id="kapasitas-judul">Kapasitas</h2>
        <span className="panel-meta">perkiraan, bukan pemakaian RAM sebenarnya</span>
      </div>
      <div className={s.capGrid}>
        <div>
          <p className="overline">RAM perkiraan</p>
          <p className={s.capValue}>
            {num(c.used_mb)} <span className="soft">/ {num(c.limit_mb)} MB</span>
          </p>
          <div
            className="progress-track"
            role="progressbar"
            aria-label="RAM perkiraan"
            aria-valuenow={Math.round(pct)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuetext={`${num(c.used_mb)} dari ${num(c.limit_mb)} MB`}
          >
            <span className="progress-fill" style={{ width: `${pct}%`, display: "block" }} />
          </div>
        </div>
        <div>
          <p className="overline">Deploy berjalan</p>
          <p className={s.capValue}>
            {c.deploying} <span className="soft">/ {c.max_deploys}</span>
          </p>
        </div>
        <div>
          <p className="overline">Batas idle</p>
          <p className={s.capValue}>
            {c.idle_minutes} <span className="soft">menit</span>
          </p>
        </div>
      </div>
    </section>
  );
}

export function AdminLabs() {
  const { data, error, reload } = useApi(api.adminLabs, [], REFRESH_MS);
  const [target, setTarget] = useState<AdminLab | null>(null);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string | null>(null);
  const [stopped, setStopped] = useState<string | null>(null);
  const closeTarget = useCallback(() => setTarget(null), []);

  const stop = async (lab: AdminLab) => {
    setStopping(true);
    setStopError(null);
    setStopped(null);
    try {
      const res = await api.adminStopLab(lab.username, lab.lab_id);
      setStopped(
        `Lab ${lab.title} milik ${lab.display_name} dimatikan.` +
          (res.archived ? ` Sesi ${res.archived} diarsipkan sebagai ditinggalkan.` : ""),
      );
      void reload();
    } catch (err) {
      setStopError(err instanceof Error ? err.message : "Lab gagal dimatikan.");
    } finally {
      setStopping(false);
      setTarget(null);
    }
  };

  const labs = data?.labs ?? [];

  return (
    <>
      <PageHeader title="Lab berjalan" overline="Admin" />
      <div className={s.toolbar}>
        <p className="soft">Daftar diperbarui otomatis tiap 10 detik. Matikan lab yang sudah ditinggalkan untuk membebaskan RAM.</p>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void reload()} disabled={stopping}>
          Muat ulang
        </button>
      </div>

      {error && <p className="notice notice-ember" role="alert">{error.message}</p>}
      {stopError && <p className="notice notice-ember" role="alert">{stopError}</p>}
      {stopped && <p className="notice" role="status">{stopped}</p>}

      {data && <Capacity c={data.capacity} />}

      {data && labs.length === 0 ? (
        <div className="empty">Tidak ada lab yang berjalan.</div>
      ) : (
        data && (
          <section className="panel">
            <div className={s.tableWrap}>
              <table className={s.table} aria-label="Lab yang berjalan">
                <thead>
                  <tr>
                    <th scope="col" className="overline">User</th>
                    <th scope="col" className="overline">Lab</th>
                    <th scope="col" className="overline">Status</th>
                    <th scope="col" className="overline">RAM</th>
                    <th scope="col" className="overline">Aktivitas terakhir</th>
                    <th scope="col" className="overline">Sesi</th>
                    <th scope="col" aria-label="Aksi" />
                  </tr>
                </thead>
                <tbody>
                  {labs.map((lab) => {
                    const reason = lab.busy ? BUSY_REASON[lab.busy] : undefined;
                    return (
                      <tr key={`${lab.username}/${lab.lab_id}`}>
                        <td>
                          <span className={s.name}>{lab.display_name}</span>
                          <span className="soft">{lab.username}</span>
                        </td>
                        <td>
                          <span className={s.name}>{lab.title}</span>
                          <span className="soft mono">{lab.lab_id}</span>
                        </td>
                        <td>
                          <Status lab={lab} />
                        </td>
                        <td className="soft">{num(lab.mem_mb)} MB</td>
                        <td className="soft">{idleText(lab.idle_s)}</td>
                        <td>{lab.session ? <span className={`soft ${s.mono}`}>{lab.session}</span> : <span className="soft">—</span>}</td>
                        <td>
                          <button
                            type="button"
                            className={`btn btn-secondary btn-sm ${s.stopButton}`}
                            disabled={stopping || lab.busy !== null}
                            title={reason}
                            aria-label={`Matikan ${lab.title} milik ${lab.display_name}`}
                            onClick={() => setTarget(lab)}
                          >
                            Matikan
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )
      )}

      {target && (
        <Modal
          title="Matikan lab ini?"
          onClose={stopping ? undefined : closeTarget}
          actions={
            <>
              <button type="button" className="btn btn-secondary" onClick={closeTarget} disabled={stopping}>
                Batal
              </button>
              <button type="button" className="btn btn-primary" onClick={() => void stop(target)} disabled={stopping}>
                {stopping ? "Mematikan…" : "Matikan lab"}
              </button>
            </>
          }
        >
          <p>
            Lab <strong>{target.title}</strong> milik {target.display_name} ({target.username}) akan dimatikan dan container-nya
            dihapus.
          </p>
          <p>
            Sesi yang belum dinilai akan diarsipkan sebagai <strong>ditinggalkan</strong>
            {target.session ? (
              <>
                {" "}
                (sesi <code>{target.session}</code>)
              </>
            ) : null}
            .
          </p>
        </Modal>
      )}
    </>
  );
}
