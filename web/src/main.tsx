import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import "./styles/global.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { AppDataProvider, useAppData } from "./lib/appData";
import { Home } from "./pages/Home";
import { Labs } from "./pages/Labs";
import { LabSession } from "./pages/LabSession";
import { Leaderboard } from "./pages/Leaderboard";
import { AdminLabs } from "./pages/AdminLabs";
import { AdminUsers } from "./pages/AdminUsers";
import { ClassProgress } from "./pages/ClassProgress";
import { ClassStudent } from "./pages/ClassStudent";
import { Learn } from "./pages/Learn";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { Progress } from "./pages/Progress";
import { Result } from "./pages/Result";

// Mode server tanpa login: semua alamat menampilkan Login. Setelah login, alamat
// yang tadi dibuka langsung tampil (tidak perlu redirect bolak-balik).
function App() {
  const { me, meError, reloadMe } = useAppData();
  if (!me) {
    return meError ? (
      <main style={{ padding: "var(--space-3xl)" }}>
        <p className="notice notice-ember">
          Server P-lab tidak bisa dihubungi: {meError.message}
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void reloadMe()}>
            Coba lagi
          </button>
        </p>
      </main>
    ) : null;
  }
  if (me.auth && !me.user) return <Login />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="labs" element={<Labs />} />
        <Route path="labs/:labId" element={<LabSession />} />
        <Route path="labs/:labId/sesi/:session" element={<Result />} />
        <Route path="progress" element={<Progress />} />
        <Route path="leaderboard" element={<Leaderboard />} />
        <Route path="belajar/:track" element={<Learn />} />
        {/* Dashboard mode Server; server tetap memeriksa role (403/404). */}
        <Route path="admin/akun" element={<AdminUsers />} />
        <Route path="admin/lab" element={<AdminLabs />} />
        <Route path="kelas" element={<ClassProgress />} />
        <Route path="kelas/:username" element={<ClassStudent />} />
        <Route path="kelas/:username/labs/:labId/sesi/:session" element={<Result />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AppDataProvider>
        <App />
      </AppDataProvider>
    </BrowserRouter>
  </StrictMode>,
);
