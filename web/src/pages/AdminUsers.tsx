import { useCallback, useId, useRef, useState } from "react";
import { Modal } from "../components/Modal";
import { PageHeader } from "../components/Layout";
import { api, ApiError, type AdminUser, type ImportResult, type Role } from "../lib/api";
import { useAppData } from "../lib/appData";
import { date as tanggal } from "../lib/format";
import { useApi } from "../lib/hooks";
import s from "./AdminUsers.module.css";

// Halaman Admin → Akun (mode Server). Semua aksi lewat /api/admin/users.
// Password acak dari server hanya dikirim sekali; dialog "secret" menampilkannya
// dan tidak bisa ditutup dengan klik di luar atau Escape, supaya admin sempat mencatat.

const ROLE_LABEL: Record<Role, string> = { admin: "Admin", guru: "Guru", siswa: "Siswa" };
const ROLE_OPTIONS: Role[] = ["siswa", "guru", "admin"];
const USERNAME_PATTERN = "[a-z0-9][a-z0-9\\-]{0,31}";

type SecretRow = { username: string; password: string | null };

type Dialog =
  | { kind: "create" }
  | { kind: "import" }
  | { kind: "edit"; user: AdminUser }
  | { kind: "toggle"; user: AdminUser }
  | { kind: "reset"; user: AdminUser }
  | {
      kind: "secret";
      title: string;
      intro: string;
      rows: SecretRow[];
      copy: string;
      copyLabel: string;
      errors?: ImportResult["errors"];
    }
  | null;

type DoneHandler = (next: Dialog, message?: string) => void;

function errorText(err: unknown) {
  return err instanceof ApiError ? err.message : "Server tidak bisa dihubungi.";
}

/** "5 menit lalu", atau tanggal kalau sudah lama. */
function ago(epoch: number | null) {
  if (!epoch) return "Belum pernah";
  const diff = Date.now() / 1000 - epoch;
  if (diff < 60) return "baru saja";
  if (diff < 3600) return `${Math.floor(diff / 60)} menit lalu`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} jam lalu`;
  if (diff < 30 * 86400) return `${Math.floor(diff / 86400)} hari lalu`;
  return tanggal(epoch);
}

/** Salin teks. Clipboard API hanya ada di konteks aman (HTTPS/localhost); selain itu pakai cara lama. */
async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* lanjut ke cara cadangan */
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  area.remove();
  return ok;
}

export function AdminUsers() {
  const { me } = useAppData();
  const self = me?.user?.username;
  const { data, error, reload } = useApi(api.adminUsers, []);
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<"" | Role>("");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const close = useCallback(() => setDialog(null), []);
  const done: DoneHandler = useCallback(
    (next, message) => {
      setDialog(next);
      if (message) setFlash(message);
      void reload();
    },
    [reload],
  );

  const users = data?.users ?? [];
  const q = query.trim().toLowerCase();
  const shown = users.filter(
    (u) =>
      (!roleFilter || u.role === roleFilter) &&
      (!q || u.username.includes(q) || u.display_name.toLowerCase().includes(q)),
  );

  return (
    <>
      <PageHeader title="Akun" overline="Admin" />

      <div className={s.toolbar}>
        <div className={s.filters}>
          <label className={s.search}>
            <span className="sr-only">Cari nama atau username</span>
            <input
              type="search"
              className={s.input}
              placeholder="Cari nama atau username"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <label className={s.select}>
            <span className="sr-only">Filter role</span>
            <select className={s.input} value={roleFilter} onChange={(e) => setRoleFilter(e.target.value as "" | Role)}>
              <option value="">Semua role</option>
              {ROLE_OPTIONS.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className={s.actions}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setDialog({ kind: "import" })}>
            Import CSV
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => setDialog({ kind: "create" })}>
            Tambah akun
          </button>
        </div>
      </div>

      {flash && (
        <p className="notice" role="status">
          {flash}
        </p>
      )}
      {error && (
        <p className="notice notice-ember" role="alert">
          {errorText(error)}
        </p>
      )}
      {!data && !error && <p className="soft">Memuat akun…</p>}

      {data && users.length === 0 && <p className="empty">Belum ada akun.</p>}
      {data && users.length > 0 && (
        <>
          <p className={s.count}>
            {shown.length} dari {users.length} akun
          </p>
          {shown.length === 0 ? (
            <p className="empty">Tidak ada akun yang cocok dengan filter.</p>
          ) : (
            <div className={s.tableWrap}>
              <table className={s.table}>
                <caption className="sr-only">Daftar akun</caption>
                <thead>
                  <tr>
                    <th scope="col">Nama</th>
                    <th scope="col">Username</th>
                    <th scope="col">Role</th>
                    <th scope="col">Status</th>
                    <th scope="col">Terakhir terlihat</th>
                    <th scope="col">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((u) => {
                    const isSelf = u.username === self;
                    return (
                      <tr key={u.username}>
                        <td>
                          {u.display_name}
                          {isSelf && <span className="soft"> · kamu</span>}
                        </td>
                        <td>
                          <code>{u.username}</code>
                        </td>
                        <td>{ROLE_LABEL[u.role]}</td>
                        <td>
                          <span className={`chip ${u.active ? "chip-accent" : "chip-ember"}`}>
                            {u.active ? "Aktif" : "Nonaktif"}
                          </span>
                        </td>
                        <td className={s.muted}>{ago(u.last_seen)}</td>
                        <td className={s.actionsCell}>
                          <div className={s.rowActions}>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              aria-label={`Ubah ${u.username}`}
                              onClick={() => setDialog({ kind: "edit", user: u })}
                            >
                              Ubah
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              aria-label={`Reset password ${u.username}`}
                              disabled={isSelf}
                              title={isSelf ? "Password akun sendiri diganti lewat CLI p-lab-admin" : undefined}
                              onClick={() => setDialog({ kind: "reset", user: u })}
                            >
                              Reset password
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              aria-label={`${u.active ? "Nonaktifkan" : "Aktifkan"} ${u.username}`}
                              disabled={isSelf}
                              title={isSelf ? "Tidak bisa menonaktifkan akun sendiri" : undefined}
                              onClick={() => setDialog({ kind: "toggle", user: u })}
                            >
                              {u.active ? "Nonaktifkan" : "Aktifkan"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {dialog?.kind === "create" && <CreateDialog onClose={close} onDone={done} />}
      {dialog?.kind === "import" && <ImportDialog onClose={close} onDone={done} />}
      {dialog?.kind === "edit" && <EditDialog user={dialog.user} self={dialog.user.username === self} onClose={close} onDone={done} />}
      {dialog?.kind === "toggle" && <ToggleDialog user={dialog.user} onClose={close} onDone={done} />}
      {dialog?.kind === "reset" && <ResetDialog user={dialog.user} onClose={close} onDone={done} />}
      {dialog?.kind === "secret" && (
        <SecretDialog
          title={dialog.title}
          intro={dialog.intro}
          rows={dialog.rows}
          copy={dialog.copy}
          copyLabel={dialog.copyLabel}
          errors={dialog.errors}
          onClose={close}
        />
      )}
    </>
  );
}

/** Dialog dengan form dan tombol kirim di footer. Tidak bisa ditutup saat request berjalan. */
function FormDialog({
  title,
  submitLabel,
  busyLabel,
  submitDisabled,
  onClose,
  onSubmit,
  children,
}: {
  title: string;
  submitLabel: string;
  busyLabel: string;
  submitDisabled?: boolean;
  onClose: () => void;
  onSubmit: () => Promise<void>;
  children: React.ReactNode;
}) {
  const id = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const requestClose = useCallback(() => {
    if (!busyRef.current) onClose();
  }, [onClose]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      await onSubmit();
    } catch (err) {
      setError(errorText(err));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  return (
    <Modal
      title={title}
      onClose={requestClose}
      actions={
        <>
          <button type="button" className="btn btn-secondary btn-sm" onClick={requestClose} disabled={busy}>
            Batal
          </button>
          <button type="submit" form={id} className="btn btn-primary btn-sm" disabled={busy || submitDisabled}>
            {busy ? busyLabel : submitLabel}
          </button>
        </>
      }
    >
      <form id={id} className={s.form} onSubmit={submit}>
        {children}
        {error && (
          <p className="notice notice-ember" role="alert">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}

function CreateDialog({ onClose, onDone }: { onClose: () => void; onDone: DoneHandler }) {
  const uid = useId();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<Role>("siswa");
  const [password, setPassword] = useState("");

  async function submit() {
    const res = await api.adminCreateUser({
      username: username.trim(),
      display_name: displayName.trim() || undefined,
      role,
      password: password || undefined,
    });
    if (res.password) {
      onDone({
        kind: "secret",
        title: "Akun dibuat",
        intro: `Akun ${res.user.username} sudah dibuat. Password acak ini hanya ditampilkan sekali.`,
        rows: [{ username: res.user.username, password: res.password }],
        copy: res.password,
        copyLabel: "Salin password",
      });
    } else {
      onDone(null, `Akun ${res.user.username} dibuat.`);
    }
  }

  return (
    <FormDialog title="Tambah akun" submitLabel="Simpan" busyLabel="Menyimpan…" onClose={onClose} onSubmit={submit}>
      <label className={s.field}>
        <span className={s.label}>Username</span>
        <input
          className={s.input}
          name="username"
          autoCapitalize="none"
          spellCheck={false}
          required
          pattern={USERNAME_PATTERN}
          title="Huruf kecil, angka, dan tanda hubung. Maksimal 32 karakter, diawali huruf atau angka."
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <span className={s.hint}>Huruf kecil, angka, dan tanda hubung. Maksimal 32 karakter.</span>
      </label>
      <label className={s.field}>
        <span className={s.label}>Nama tampilan</span>
        <input className={s.input} name="display_name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
      </label>
      <label className={s.field}>
        <span className={s.label}>Role</span>
        <select className={s.input} name="role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {ROLE_OPTIONS.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
      </label>
      <label className={s.field} htmlFor={`${uid}-pw`}>
        <span className={s.label}>Password (opsional)</span>
        <input
          id={`${uid}-pw`}
          className={s.input}
          name="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <span className={s.hint}>Kosongkan untuk password acak. Password acak ditampilkan sekali setelah akun dibuat.</span>
      </label>
    </FormDialog>
  );
}

const CSV_EXAMPLE = "username,display_name,role,password\nalice,Alice A,siswa,\nbob,Bob B,guru,rahasia-bob";

function ImportDialog({ onClose, onDone }: { onClose: () => void; onDone: DoneHandler }) {
  const uid = useId();
  const [csv, setCsv] = useState("");
  const [role, setRole] = useState<Role>("siswa");

  async function submit() {
    const res = await api.adminImportUsers(csv, role);
    const failed = res.errors.length;
    onDone({
      kind: "secret",
      title: "Hasil import",
      intro:
        `${res.created.length} akun dibuat${failed ? `, ${failed} baris gagal` : ""}. ` +
        "Password acak hanya ditampilkan sekali. Akun dengan password dari CSV tidak menampilkan password.",
      rows: res.created.map((c) => ({ username: c.username, password: c.password })),
      copy: res.created.filter((c) => c.password !== null).map((c) => `${c.username},${c.password}`).join("\n"),
      copyLabel: "Salin semua",
      errors: res.errors,
    });
  }

  return (
    <FormDialog
      title="Import CSV"
      submitLabel="Import"
      busyLabel="Mengimpor…"
      submitDisabled={!csv.trim()}
      onClose={onClose}
      onSubmit={submit}
    >
      <label className={s.field} htmlFor={`${uid}-csv`}>
        <span className={s.label}>Isi CSV</span>
        <textarea
          id={`${uid}-csv`}
          className={s.textarea}
          spellCheck={false}
          rows={8}
          value={csv}
          onChange={(e) => setCsv(e.target.value)}
        />
      </label>
      <div>
        <p className={s.hint}>Baris pertama wajib berisi header. Contoh:</p>
        <pre className={s.code}>
          <code>{CSV_EXAMPLE}</code>
        </pre>
        <p className={s.hint}>Kolom role dan password boleh kosong. Role kosong memakai role default; password kosong dibuatkan acak.</p>
      </div>
      <label className={s.field}>
        <span className={s.label}>Role default</span>
        <select className={s.input} value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {ROLE_OPTIONS.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
      </label>
    </FormDialog>
  );
}

function EditDialog({
  user,
  self,
  onClose,
  onDone,
}: {
  user: AdminUser;
  self: boolean;
  onClose: () => void;
  onDone: DoneHandler;
}) {
  const [name, setName] = useState(user.display_name);
  const [role, setRole] = useState<Role>(user.role);

  async function submit() {
    const body: { display_name?: string; role?: Role } = {};
    const trimmed = name.trim();
    if (trimmed !== user.display_name) body.display_name = trimmed;
    if (!self && role !== user.role) body.role = role;
    if (Object.keys(body).length === 0) {
      onDone(null);
      return;
    }
    await api.adminUpdateUser(user.username, body);
    onDone(null, `Akun ${user.username} diperbarui.`);
  }

  return (
    <FormDialog
      title={`Ubah ${user.username}`}
      submitLabel="Simpan"
      busyLabel="Menyimpan…"
      submitDisabled={!name.trim()}
      onClose={onClose}
      onSubmit={submit}
    >
      <label className={s.field}>
        <span className={s.label}>Nama tampilan</span>
        <input className={s.input} name="display_name" required value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className={s.field}>
        <span className={s.label}>Role</span>
        <select
          className={s.input}
          name="role"
          value={role}
          disabled={self}
          onChange={(e) => setRole(e.target.value as Role)}
        >
          {ROLE_OPTIONS.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
        {self && <span className={s.hint}>Role akun sendiri tidak bisa diubah.</span>}
      </label>
    </FormDialog>
  );
}

function ToggleDialog({ user, onClose, onDone }: { user: AdminUser; onClose: () => void; onDone: DoneHandler }) {
  const activate = !user.active;

  async function submit() {
    const res = await api.adminUpdateUser(user.username, { active: activate });
    const stopped = res.stopped_labs.length;
    const skipped = res.skipped_labs.length;
    onDone(
      null,
      activate
        ? `Akun ${user.username} diaktifkan.`
        : `Akun ${user.username} dinonaktifkan.` +
            (stopped ? ` ${stopped} lab yang berjalan ikut dimatikan.` : "") +
            (skipped ? ` ${skipped} lab sedang sibuk dan akan dimatikan otomatis setelah selesai.` : ""),
    );
  }

  return (
    <FormDialog
      title={activate ? `Aktifkan ${user.username}?` : `Nonaktifkan ${user.username}?`}
      submitLabel={activate ? "Aktifkan" : "Nonaktifkan"}
      busyLabel="Memproses…"
      onClose={onClose}
      onSubmit={submit}
    >
      <p className={s.hint}>
        {activate
          ? "Akun bisa login lagi dengan password yang sama."
          : "Akun tidak bisa login. Sesi login yang sedang aktif langsung dihentikan, dan lab yang sedang berjalan milik akun ini ikut dimatikan. Akun bisa diaktifkan lagi nanti."}
      </p>
    </FormDialog>
  );
}

function ResetDialog({ user, onClose, onDone }: { user: AdminUser; onClose: () => void; onDone: DoneHandler }) {
  async function submit() {
    const res = await api.adminResetPassword(user.username);
    if (res.password) {
      onDone({
        kind: "secret",
        title: `Password baru ${user.username}`,
        intro: "Password acak ini hanya ditampilkan sekali. Semua sesi login akun ini sudah dihentikan.",
        rows: [{ username: user.username, password: res.password }],
        copy: res.password,
        copyLabel: "Salin password",
      });
    } else {
      onDone(null, `Password ${user.username} direset.`);
    }
  }

  return (
    <FormDialog title={`Reset password ${user.username}?`} submitLabel="Reset" busyLabel="Mereset…" onClose={onClose} onSubmit={submit}>
      <p className={s.hint}>
        Password lama tidak berlaku lagi dan semua sesi login akun ini dihentikan, termasuk sesi kamu jika ini akun sendiri.
        Password acak baru ditampilkan sekali.
      </p>
    </FormDialog>
  );
}

/** Menampilkan password sekali. Tidak bisa ditutup dengan klik luar atau Escape. */
function SecretDialog({
  title,
  intro,
  rows,
  copy,
  copyLabel,
  errors,
  onClose,
}: {
  title: string;
  intro: string;
  rows: SecretRow[];
  copy: string;
  copyLabel: string;
  errors?: ImportResult["errors"];
  onClose: () => void;
}) {
  const [status, setStatus] = useState<"idle" | "ok" | "fail">("idle");

  async function copyAll() {
    setStatus((await copyToClipboard(copy)) ? "ok" : "fail");
  }

  return (
    <Modal
      title={title}
      actions={
        <button type="button" className="btn btn-primary btn-sm" onClick={onClose}>
          Sudah saya catat
        </button>
      }
    >
      <p className="notice notice-ember" role="note">
        Catat sekarang. Password tidak bisa dilihat lagi setelah dialog ini ditutup.
      </p>
      <p>{intro}</p>
      {rows.length > 0 && (
        <table className={s.secretTable}>
          <caption className="sr-only">Akun dan password</caption>
          <thead>
            <tr>
              <th scope="col">Username</th>
              <th scope="col">Password</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.username}>
                <td>
                  <code>{r.username}</code>
                </td>
                <td>{r.password ? <code className={s.secret}>{r.password}</code> : <span className="soft">sesuai CSV</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {copy && (
        <div className={s.copyRow}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={copyAll}>
            {copyLabel}
          </button>
          <span className="soft" role="status" aria-live="polite">
            {status === "ok" && "Tersalin."}
            {status === "fail" && "Gagal menyalin. Pilih teks di tabel lalu salin manual."}
          </span>
        </div>
      )}
      {errors && errors.length > 0 && (
        <section className={s.errors}>
          <h3 className={s.heading}>Baris yang gagal</h3>
          <ul>
            {errors.map((e) => (
              <li key={`${e.line}-${e.message}`}>
                Baris {e.line}: {e.message}
              </li>
            ))}
          </ul>
        </section>
      )}
    </Modal>
  );
}
