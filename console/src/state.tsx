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

/** Coming back from Google: the engine put a token (or an error) in the URL
 *  fragment, which no server ever sees. Keep the token, drop the fragment. */
function takeLoginFragment(): { error: string | null; twofa: string | null } {
  try {
    const h = new URLSearchParams(window.location.hash.slice(1));
    const token = h.get("token"), error = h.get("error"), twofa = h.get("twofa");
    if (!token && !error && !twofa) return { error: null, twofa: null };
    if (token) setToken(token);
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    return { error, twofa };
  } catch { return { error: null, twofa: null }; }
}
const FRAGMENT = typeof window === "undefined" ? { error: null, twofa: null } : takeLoginFragment();
const LOGIN_ERROR = FRAGMENT.error;
/** Google passed, two-step sign-in is on: the ticket for the authenticator code. */
const LOGIN_TWOFA = FRAGMENT.twofa;

interface AppState {
  /** Why a Google sign-in was turned away ("not-allowed", "google-failed"…), once. */
  loginError: string | null;
  /** Google passed and two-step sign-in is on: the ticket for the second step, once. */
  loginTicket: string | null;
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
  /** The public demo (sign-in off on a public server), or no engine at all: nothing can be changed from here. */
  readOnly: boolean;
  signIn: (token: string, user: User) => void;
  signOut: () => void;
  /** POST /api/auth/logout (every device), then forget the token here. */
  signOutEverywhere: () => Promise<void>;
  sampleView: boolean;            // the Sample switch: show the made-up shop instead of the engine
  setSampleView: (on: boolean) => void;
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
  // On with ?sample=1 (a link for a teacher or a client) or from the switch; remembered per browser.
  const [sampleView, setSampleState] = useState<boolean>(() => {
    try {
      if (new URLSearchParams(window.location.search).get("sample") === "1") { localStorage.setItem("haanji.sample", "1"); return true; }
      return localStorage.getItem("haanji.sample") === "1";
    } catch { return false; }
  });
  const setSampleView = useCallback((on: boolean) => {
    try { if (on) localStorage.setItem("haanji.sample", "1"); else localStorage.removeItem("haanji.sample"); } catch { /* not remembered */ }
    setSampleState(on);
  }, []);

  // One status round-trip, then (with auth on and a token) "who am I". All
  // state lands in the continuation, never synchronously in an effect.
  const refresh = useCallback((): Promise<void> =>
    engine.status().then(async (s) => {
      setStatus(s);
      setChecked(true);
      if (s?.auth?.enabled && getToken()) {
        try {
          const me = await engine.me();
          setUser(me.user);
          // A device in use keeps its sign-in: the engine renews a token older than a week.
          engine.refreshToken().then((r) => { if (r.token && r.token !== getToken()) setToken(r.token); }).catch(() => undefined);
        } catch { setUser(null); }
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
    // Sample data only when asked for (the switch or ?sample=1): an engine that is
    // still waking up (Render's free plan takes 30-60 s) is said so, with a way to
    // wait or to look at the sample shop meanwhile, never swapped silently.
    const mode: Mode = sampleView ? "demo" : !checked || (authOn && !authChecked) ? "checking" : status ? "live" : "offline";
    const isOwner = status && !sampleView ? (!authOn || user?.role === "owner") : mode === "demo";
    const readOnly = sampleView || (status ? !!status.demo_readonly : mode !== "live");
    return {
      status, online: !!status, checked, mode, pack,
      packs: allowed(status ? status.packs : SAMPLE_STATUS.packs), setPack, refresh,
      authRequired: authOn && authChecked && !user,
      user, isOwner, readOnly, signIn, signOut, signOutEverywhere, sampleView, setSampleView,
      loginError: LOGIN_ERROR,
      loginTicket: LOGIN_TWOFA,
    };
  }, [status, checked, pack, setPack, refresh, allowed, authChecked, hasToken, user, signIn, signOut, signOutEverywhere, sampleView, setSampleView]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}
