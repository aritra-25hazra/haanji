import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { engine, getToken, setToken } from "./engine";
import { SAMPLE_STATUS } from "./sample";
import type { Status, User } from "./types";

interface AppState {
  status: Status | null;
  online: boolean;
  checked: boolean;
  pack: string;
  packs: string[];
  setPack: (pack: string) => void;
  refresh: () => Promise<void>;
  authRequired: boolean;          // engine wants a sign-in and we have none
  user: User | null;
  signIn: (token: string, user: User) => void;
  signOut: () => void;
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
  const [user, setUser] = useState<User | null>(null);
  const [authChecked, setAuthChecked] = useState(false);

  const refresh = useCallback(async () => {
    const s = await engine.status();
    setStatus(s);
    setChecked(true);
    if (s?.auth?.enabled) {
      if (getToken()) {
        try { const me = await engine.me(); setUser(me.user); } catch { setUser(null); }
      } else { setUser(null); }
    } else { setUser(null); }
    setAuthChecked(true);
    if (s && !s.packs.includes(pack)) setPackState(s.default_pack);
  }, [pack]);

  useEffect(() => {
    const out = () => setUser(null);
    window.addEventListener("haanji:signed-out", out);
    return () => window.removeEventListener("haanji:signed-out", out);
  }, []);
  const signIn = useCallback((token: string, u: User) => { setToken(token); setUser(u); }, []);
  const signOut = useCallback(() => { setToken(null); setUser(null); }, []);

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

  const allowed = useCallback((all: string[]) => (user && !user.packs.includes("*") ? all.filter((p) => user.packs.includes(p)) : all), [user]);
  const value = useMemo<AppState>(() => ({
    status, online: !!status, checked, pack,
    packs: allowed(status ? status.packs : SAMPLE_STATUS.packs), setPack, refresh,
    authRequired: !!status?.auth?.enabled && authChecked && !user,
    user, signIn, signOut,
  }), [status, checked, pack, setPack, refresh, allowed, authChecked, user, signIn, signOut]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}
