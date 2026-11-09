import { useState } from "react";
import { api, ApiError } from "../lib/api";
import { useAppData } from "../lib/appData";
import s from "./Login.module.css";

// Halaman masuk mode Server. Tidak ada tombol daftar: akun dibuat admin
// (platform/p-lab-admin). Setelah login, /api/me dimuat ulang dan alamat yang
// sedang dibuka langsung tampil.

export function Login() {
  const { reloadMe } = useAppData();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(username.trim(), password);
      await reloadMe();
    } catch (err) {
      // 401 = salah, 429 = terlalu banyak percobaan (pesan dari server sudah berbahasa Indonesia).
      setError(err instanceof ApiError ? err.message : "Server tidak bisa dihubungi.");
      setPassword("");
      setBusy(false);
    }
  }

  return (
    <main className={s.page}>
      <form className={`panel ${s.card}`} onSubmit={submit} aria-labelledby="login-title">
        <div className={s.brand}>
          <span className={s.brandMark} aria-hidden="true">
            P
          </span>
          <span className={s.brandText}>P-lab</span>
        </div>
        <div className={s.heading}>
          <h1 id="login-title" className={s.title}>
            Masuk
          </h1>
          <p className="soft">Pakai akun yang diberikan admin lab.</p>
        </div>

        <label className={s.field}>
          <span className={s.label}>Username</span>
          <input
            className={s.input}
            name="username"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            autoFocus
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </label>
        <label className={s.field}>
          <span className={s.label}>Password</span>
          <input
            className={s.input}
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {error && (
          <p className="notice notice-ember" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="btn btn-primary" disabled={busy || !username.trim() || !password}>
          {busy ? "Memeriksa…" : "Masuk"}
        </button>
        <p className={s.help}>Lupa password? Minta admin lab untuk menggantinya.</p>
      </form>
    </main>
  );
}
