import { FitAddon } from "@xterm/addon-fit";
import { Terminal as Xterm } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { useCallback, useEffect, useRef, useState } from "react";
import s from "./Terminal.module.css";

// Terminal satu node: xterm.js + WebSocket ke platform/termbridge.py (PTY yang menjalankan
// lab-shell, jadi perekaman tetap di sisi server). Satu port, cookie login ikut otomatis.
// Protokol: server kirim binary (output mentah); klien kirim JSON text
// {"type":"input"|"resize"}. Komponen dibiarkan mounted saat tab disembunyikan supaya
// shell tetap hidup; `active` hanya memicu fit ulang (ukuran 0 saat hidden).

// Sama dengan warna terminal lama (TTYD_THEME di server.py) = token tokens.css.
const THEME = {
  background: "#0B0E0C",
  foreground: "#ECF3EE",
  cursor: "#5FF0B0",
  cursorAccent: "#04120C",
  selectionBackground: "#1D5A41",
  green: "#5FF0B0",
  brightGreen: "#5FF0B0",
  yellow: "#F0BD4F",
  red: "#FF7B47",
};

type Status = "connecting" | "open" | "closed" | "denied";

const DENIED: Record<number, string> = {
  4401: "Sesi login berakhir. Muat ulang halaman dan masuk lagi.",
  4404: "Node tidak berjalan. Cek lab, atau reset lab kalau container mati.",
  4429: "Terlalu banyak terminal terbuka untuk lab ini. Tutup tab lain lalu sambung ulang.",
};

export function Terminal({ labId, node, active }: { labId: string; node: string; active: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  const term = useRef<Xterm | null>(null);
  const fit = useRef<FitAddon | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const activeRef = useRef(active);
  activeRef.current = active;
  const [status, setStatus] = useState<Status>("connecting");
  const [deniedCode, setDeniedCode] = useState(0);

  const send = (msg: object) => {
    const ws = socket.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  };

  const connect = useCallback(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/api/labs/${labId}/term/${encodeURIComponent(node)}`);
    ws.binaryType = "arraybuffer";
    socket.current = ws;
    setStatus("connecting");
    ws.onopen = () => {
      setStatus("open");
      const t = term.current;
      if (t && t.cols > 0) ws.send(JSON.stringify({ type: "resize", cols: t.cols, rows: t.rows }));
      if (activeRef.current) t?.focus();
    };
    // Uint8Array: xterm menyambung karakter UTF-8 yang terpotong antar frame.
    ws.onmessage = (e) => e.data instanceof ArrayBuffer && term.current?.write(new Uint8Array(e.data));
    ws.onclose = (e) => {
      if (socket.current !== ws) return; // sudah diganti sambungan baru
      if (DENIED[e.code]) {
        setDeniedCode(e.code);
        setStatus("denied");
      } else {
        setStatus("closed");
      }
    };
  }, [labId, node]);

  useEffect(() => {
    const t = new Xterm({
      theme: THEME,
      fontFamily: "'JetBrains Mono', ui-monospace, monospace",
      fontSize: 13,
      cursorBlink: true,
      scrollback: 5000,
    });
    const f = new FitAddon();
    t.loadAddon(f);
    t.open(host.current!);
    term.current = t;
    fit.current = f;

    t.onData((data) => send({ type: "input", data }));
    t.onResize(({ cols, rows }) => send({ type: "resize", cols, rows }));

    // Kontainer hidden (tab lain) berukuran 0: jangan fit, nanti salah hitung baris/kolom.
    const refit = () => {
      const el = host.current;
      if (el && el.clientWidth > 0 && el.clientHeight > 0) f.fit();
    };
    const observer = new ResizeObserver(refit);
    observer.observe(host.current!);
    // Font belum termuat saat open() → ukuran sel salah; fit ulang begitu siap.
    document.fonts?.load("13px 'JetBrains Mono'").then(refit, () => {});
    refit();

    connect();
    return () => {
      observer.disconnect();
      const ws = socket.current;
      socket.current = null;
      ws?.close(); // server menutup PTY + proses saat WebSocket putus
      t.dispose();
      term.current = fit.current = null;
    };
  }, [connect]);

  // Tab jadi aktif: fit ulang (ukuran berubah selagi hidden) dan fokus.
  useEffect(() => {
    if (!active) return;
    const id = requestAnimationFrame(() => {
      fit.current?.fit();
      term.current?.focus();
    });
    return () => cancelAnimationFrame(id);
  }, [active]);

  const reconnect = () => {
    term.current?.reset();
    connect();
    if (term.current) fit.current?.fit();
  };

  return (
    <div className={s.wrap}>
      <div ref={host} className={s.host} />
      {status !== "open" && (
        <div className={s.overlay} role="status">
          {status === "connecting" && <span className="soft">Menyambung ke {node}…</span>}
          {status === "closed" && (
            <>
              <span>Terminal {node} terputus.</span>
              <button type="button" className="btn btn-secondary btn-sm" onClick={reconnect}>
                Sambung ulang
              </button>
            </>
          )}
          {status === "denied" && (
            <>
              <span className="ember">{DENIED[deniedCode]}</span>
              {deniedCode !== 4401 && (
                <button type="button" className="btn btn-secondary btn-sm" onClick={reconnect}>
                  Coba lagi
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
