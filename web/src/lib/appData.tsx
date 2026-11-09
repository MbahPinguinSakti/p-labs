import { createContext, useCallback, useContext, useEffect } from "react";
import { api, UNAUTHORIZED_EVENT, type LabCard, type Me } from "./api";
import { useApi } from "./hooks";

// Data yang dipakai di banyak halaman (sidebar "Sesi aktif", akun). Di-poll ringan
// supaya sidebar ikut berubah saat sesi dimulai/dinilai dari halaman lain atau CLI.
type AppData = {
  me: Me | null;
  meError: Error | null;
  reloadMe: () => Promise<void>;
  logout: () => Promise<void>;
  labs: LabCard[] | null;
  labsError: Error | null;
  reloadLabs: () => Promise<void>;
};

const Ctx = createContext<AppData>({
  me: null,
  meError: null,
  reloadMe: async () => {},
  logout: async () => {},
  labs: null,
  labsError: null,
  reloadLabs: async () => {},
});

/** Boleh memanggil API lain? Pribadi selalu; server hanya setelah login. */
export const signedIn = (me: Me | null) => Boolean(me && (!me.auth || me.user));

export function AppDataProvider({ children }: { children: React.ReactNode }) {
  const me = useApi(api.me, []);
  const ready = signedIn(me.data);
  // Belum login: jangan poll /labs (pasti 401, dan 401 memicu muat ulang /me).
  const labs = useApi(() => (ready ? api.labs() : Promise.resolve(null)), [ready], ready ? 5000 : undefined);
  const reloadMe = me.reload;

  useEffect(() => {
    const onUnauthorized = () => void reloadMe();
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [reloadMe]);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      await reloadMe();
    }
  }, [reloadMe]);

  return (
    <Ctx.Provider
      value={{
        me: me.data,
        meError: me.error,
        reloadMe,
        logout,
        labs: labs.data,
        labsError: labs.error,
        reloadLabs: labs.reload,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export const useAppData = () => useContext(Ctx);

export const activeLab = (labs: LabCard[] | null) => labs?.find((lab) => lab.active_session) ?? null;
