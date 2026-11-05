import { createContext, useContext } from "react";
import { api, type LabCard, type Me } from "./api";
import { useApi } from "./hooks";

// Data yang dipakai di banyak halaman (sidebar "Sesi aktif", akun). Di-poll ringan
// supaya sidebar ikut berubah saat sesi dimulai/dinilai dari halaman lain atau CLI.
type AppData = {
  me: Me | null;
  labs: LabCard[] | null;
  labsError: Error | null;
  reloadLabs: () => Promise<void>;
};

const Ctx = createContext<AppData>({ me: null, labs: null, labsError: null, reloadLabs: async () => {} });

export function AppDataProvider({ children }: { children: React.ReactNode }) {
  const me = useApi(api.me, []);
  const labs = useApi(api.labs, [], 5000);
  return (
    <Ctx.Provider value={{ me: me.data, labs: labs.data, labsError: labs.error, reloadLabs: labs.reload }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAppData = () => useContext(Ctx);

export const activeLab = (labs: LabCard[] | null) => labs?.find((lab) => lab.active_session) ?? null;
