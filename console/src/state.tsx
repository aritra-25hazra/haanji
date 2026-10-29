import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { engine, getToken, setToken } from "./engine";
import { SAMPLE_STATUS } from "./sample";
import type { Status, User } from "./types";

/**
 * What the console is looking at.
 *  - checking: the status call (and, with auth on, the "who am I" call) has not answered yet.
 *  - live:     the engine answered; every page reads from it.
 *  - demo:     the engine is unreachable and nobody is signed in — the public demo; pages show sample data, labelled.
 *  - offline:  the engine is unreachable but a token exists (a signed-in owner): never show sample numbers as if they were theirs.
 */
export type Mode = "checking" | "live" | "demo" | "offline";

interface AppState {
  status: Status | null;
  online: boolean;
  checked: boolean;
  mode: Mode;
  pack: string;
  packs: string[];
  setPack: (pack: string) => void;
  refresh: () => Promise<void>;
  authRequired: boolean;          // engine wants a sign-in and we have none
  user: User | null;
  /** Owner-only controls show for the owner, and for everyone when the engine runs with auth off. The server enforces; this is UX. */
  isOwner: boolean;
  signIn: (token: string, user: User) => void;
  signOut: () => void;
  /** POST /api/auth/logout (every device), then forget the token here. */
  signOutEverywhere: () => Promise<void>;
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
  const [hasToken, setHasToken] = useState<boolean>(() => !!getToken());

  // One status round-trip, then (with auth on and a token) "who am I". All
  // state lands in the continuation, never synchronously in an effect.
  const refresh = useCallback((): Promise<void> =>
    engine.status().then(async (s) => {
      setStatus(s);
      setChecked(true);
      if (s?.auth?.enabled && getToken()) {
        try { const me = await engine.me(); setUser(me.user); } catch { setUser(null); }
      } else {
        setUser(null);
      }
      setHasToken(!!getToken());
      setAuthChecked(true);
      if (s && !s.packs.includes(pack)) setPackState(s.default_pack);
    }), [pack]);

  useEffect(() => {
    const out = () => { setUser(null); setHasToken(false); };
    window.addEventListener("haanji:signed-out", out);
    return () => window.removeEventListener("haanji:signed-out", out);
  }, []);
  const signIn = useCallback((token: string, u: User) => { setToken(token); setHasToken(true); setUser(u); }, []);
  const signOut = useCallback(() => { setToken(null); setHasToken(false); setUser(null); }, []);
  const signOutEverywhere = useCallback(async () => {
    try { await engine.logout(); } finally { setToken(null); setHasToken(false); setUser(null); }
  }, []);

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
  const value = useMemo<AppState>(() => {
    const authOn = !!status?.auth?.enabled;
    const mode: Mode = !checked || (authOn && !authChecked) ? "checking" : status ? "live" : hasToken ? "offline" : "demo";
    const isOwner = status ? (!authOn || user?.role === "owner") : mode === "demo";
    return {
      status, online: !!status, checked, mode, pack,
      packs: allowed(status ? status.packs : SAMPLE_STATUS.packs), setPack, refresh,
      authRequired: authOn && authChecked && !user,
      user, isOwner, signIn, signOut, signOutEverywhere,
    };
  }, [status, checked, pack, setPack, refresh, allowed, authChecked, hasToken, user, signIn, signOut, signOutEverywhere]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}
