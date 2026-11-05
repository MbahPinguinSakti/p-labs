import { useCallback, useEffect, useRef, useState } from "react";
import type { LiveState } from "./api";

/** Jalankan fetcher saat mount dan saat deps berubah; `reload` untuk memuat ulang. */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = [], pollMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const reload = useCallback(async () => {
    try {
      const value = await fetcherRef.current();
      setData(value);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    reload();
    if (!pollMs) return;
    const timer = setInterval(reload, pollMs);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, reload };
}

/** State sesi live lewat WebSocket; tersambung ulang otomatis kalau putus. */
export function useLiveSession(labId: string | undefined) {
  const [state, setState] = useState<LiveState | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!labId) return;
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${proto}://${location.host}/api/labs/${labId}/ws`);
      socket.onopen = () => setConnected(true);
      socket.onmessage = (event) => setState(JSON.parse(event.data));
      socket.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1500);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, [labId]);

  return { state, connected };
}

/** Detik sekarang (epoch), diperbarui tiap detik. */
export function useNow(active = true) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

/** State kecil per-browser (mis. modul yang sudah dibaca). Aman kalau storage diblokir. */
export function useStoredSet(key: string) {
  const [value, setValue] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(key) || "[]"));
    } catch {
      return new Set();
    }
  });
  const toggle = useCallback(
    (item: string) => {
      setValue((prev) => {
        const next = new Set(prev);
        if (next.has(item)) next.delete(item);
        else next.add(item);
        try {
          localStorage.setItem(key, JSON.stringify([...next]));
        } catch {
          /* storage tidak tersedia: tetap jalan di memori */
        }
        return next;
      });
    },
    [key],
  );
  return [value, toggle] as const;
}
