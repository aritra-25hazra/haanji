import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { engine } from "./engine";
import { SAMPLE_STATUS } from "./sample";
import type { Status } from "./types";

interface AppState {
  status: Status | null;
  online: boolean;
  checked: boolean;
  pack: string;
  packs: string[];
  setPack: (pack: string) => void;
  refresh: () => Promise<void>;
}

const KEY = "haanji.pack";
const Ctx = createContext<AppState | null>(null);

function stored(): string {
  try { return localStorage.getItem(KEY) || SAMPLE_STATUS.default_pack; } catch { return SAMPLE_STATUS.default_pack; }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [checked, setChecked] = useState(false);
  const [pack, setPackState] = useState<string>(stored);

  const refresh = useCallback(async () => {
    const s = await engine.status();
    setStatus(s);
    setChecked(true);
    if (s && !s.packs.includes(pack)) setPackState(s.default_pack);
  }, [pack]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (status) return;
    const t = setInterval(() => { void refresh(); }, 20_000);   // keep trying while offline
    return () => clearInterval(t);
  }, [status, refresh]);

  const setPack = useCallback((p: string) => {
    try { localStorage.setItem(KEY, p); } catch { /* private mode: not remembered */ }
    setPackState(p);
  }, []);

  const value = useMemo<AppState>(() => ({
    status, online: !!status, checked, pack,
    packs: status ? status.packs : SAMPLE_STATUS.packs, setPack, refresh,
  }), [status, checked, pack, setPack, refresh]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}
