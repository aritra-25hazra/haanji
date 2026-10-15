/**
 * The only way the console talks to the engine. Every path goes through
 * /engine/, which Vite proxies in development, Vercel rewrites in production
 * and nginx proxies in the compose stack.
 */
import type {
  CallRow, Export, Insights, Lexicon, PackSummary, Status, Turn, Verdict,
  Digest,
  Anchors,
  Draft,
  DraftRequest,
  LiveEvent,
  User,
  Ops,
  CustomerRecord,
} from "./types";

export const ENGINE_BASE = "/engine";

export function enginePath(path: string): string {
  return `${ENGINE_BASE}/${path.replace(/^\/+/, "")}`;
}

export class EngineError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "EngineError";
  }
}

const TOKEN_KEY = "haanji.token";
export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(token: string | null): void {
  try { if (token) localStorage.setItem(TOKEN_KEY, token); else localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const r = await fetch(enginePath(path), {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init?.headers ?? {}) },
  });
  if (r.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event("haanji:signed-out"));
  }
  if (!r.ok) throw new EngineError(r.status, (await r.text()) || r.statusText);
  return (await r.json()) as T;
}

const q = (pack: string) => `pack=${encodeURIComponent(pack)}`;

export const engine = {
  /** null means the engine could not be reached; every page then falls back. */
  status: async (): Promise<Status | null> => {
    try {
      return await request<Status>("api/status", { signal: AbortSignal.timeout(4000) });
    } catch {
      return null;
    }
  },
  insights: (pack: string) => request<Insights>(`api/insights?${q(pack)}`),
  calls: (pack: string) => request<{ conversations: CallRow[] }>(`api/conversations?${q(pack)}`),
  call: (pack: string, id: string) =>
    request<CallRow>(`api/conversations/${encodeURIComponent(id)}?${q(pack)}`),
  export: (pack: string) => request<Export>(`api/receipts/export?${q(pack)}`),
  lexicon: (pack: string, probe?: string) =>
    request<Lexicon>(`api/lexicon?${q(pack)}${probe ? `&probe=${encodeURIComponent(probe)}` : ""}`),
  packs: () => request<{ packs: PackSummary[] }>("api/packs"),
  draft: (body: DraftRequest) => request<Draft>("api/packs/draft", { method: "POST", body: JSON.stringify(body) }),
  digest: (pack: string) => request<Digest>(`api/digest?${q(pack)}`),
  sendDigest: (pack: string) => request<{ sent: boolean; to: string; text: string }>(`api/digest/send?${q(pack)}`, { method: "POST" }),
  anchors: (pack: string) => request<Anchors>(`api/anchors?${q(pack)}`),
  requestOtp: (phone: string) => request<{ sent: boolean; channel: string; dev_code?: string }>("api/auth/otp", { method: "POST", body: JSON.stringify({ phone }) }),
  verifyOtp: (phone: string, code: string) => request<{ token: string; user: User }>("api/auth/verify", { method: "POST", body: JSON.stringify({ phone, code }) }),
  me: () => request<{ enabled: boolean; user: User | null }>("api/auth/me"),
  users: () => request<{ users: User[] }>("api/auth/users"),
  addUser: (u: { phone: string; role: string; packs: string[]; name: string }) => request<{ user: User }>("api/auth/users", { method: "POST", body: JSON.stringify(u) }),
  removeUser: (phone: string) => request<{ removed: boolean }>(`api/auth/users/${encodeURIComponent(phone)}`, { method: "DELETE" }),
  ops: (pack: string) => request<Ops>(`api/ops?${q(pack)}`),
  customerRecord: (pack: string, phone: string) => request<CustomerRecord>(`api/privacy/customer/${encodeURIComponent(phone)}?${q(pack)}`),
  eraseCustomer: (pack: string, phone: string) => request<Record<string, number | boolean>>(`api/privacy/customer/${encodeURIComponent(phone)}?${q(pack)}`, { method: "DELETE" }),
  privacyPolicy: () => request<{ retention_days: number; consent_line: string | null; vault: { keys: number; shredded: number } }>("api/privacy/policy"),
  feedUrl: (pack: string) => request<{ pack: string; url: string; webcal: string }>(`api/calendar/feed-url?${q(pack)}`),
  googleStatus: (pack: string) => request<{ configured: boolean; connected: boolean; connected_at: string | null; redirect_uri: string }>(`api/google/status?${q(pack)}`),
  googleConnect: (pack: string) => request<{ url: string }>(`api/google/connect?${q(pack)}`),
  googleDisconnect: (pack: string) => request<{ disconnected: boolean }>(`api/google/disconnect?${q(pack)}`, { method: "DELETE" }),
  devanagari: (texts: string[]) => request<{ texts: string[]; approximate: boolean }>("api/devanagari", { method: "POST", body: JSON.stringify({ texts }) }),
  recentEvents: (pack: string, since: number) =>
    request<{ events: LiveEvent[]; latest: number; live_sessions: number }>(`api/events/recent?${q(pack)}&since=${since}`),
  packYaml: (id: string) => request<{ pack_id: string; yaml: string }>(`api/packs/${encodeURIComponent(id)}`),
  validate: (yaml: string) =>
    request<{ ok: boolean; problems: string[] }>("api/packs/validate",
      { method: "POST", body: JSON.stringify({ yaml }) }),
  save: (id: string, yaml: string) =>
    request<{ ok: boolean; problems: string[]; backup: string }>(`api/packs/${encodeURIComponent(id)}`,
      { method: "PUT", body: JSON.stringify({ yaml }) }),
  selftest: (id: string) =>
    request<{ ok: boolean; results: { passed: boolean; line: string }[]; summary: string }>(
      `api/packs/${encodeURIComponent(id)}/selftest`, { method: "POST" }),
};

// ── pure helpers (unit-tested) ──────────────────────────────────────────────

function normaliseTurn(t: Partial<Turn>): Turn {
  return {
    heard: t.heard ?? "",
    corrected: t.corrected ?? t.heard ?? "",
    said: t.said ?? "",
    tools: t.tools ?? [],
    speculation_hits: t.speculation_hits ?? [],
    guard: t.guard ?? null,
    latency_ms: t.latency_ms ?? null,
    interrupted: !!t.interrupted,
    corrections: t.corrections ?? [],
  };
}

export function parseTurns(json: string | null | undefined): Turn[] {
  try {
    const v: unknown = JSON.parse(json || "[]");
    return Array.isArray(v) ? v.map((t) => normaliseTurn(t as Partial<Turn>)) : [];
  } catch {
    return [];
  }
}

export function parseReceipts(json: string | null | undefined): string[] {
  try {
    const v: unknown = JSON.parse(json || "[]");
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  return ms < 1 ? "<1 ms" : `${Math.round(ms)} ms`;
}

/** The same single-field edit the public verifier page makes, on a copy. */
export function tamper(exp: Export): { edited: Export; seq: number } {
  const edited: Export = JSON.parse(JSON.stringify(exp));
  const victim = edited.receipts[Math.floor(edited.receipts.length / 2)];
  if (!victim) return { edited, seq: 0 };
  try {
    const args = JSON.parse(victim.action_args);
    if (args.time) args.time = "18:00";
    else if (args.service) args.service = "dental implant";
    else args.__edited = true;
    victim.action_args = JSON.stringify(args);
  } catch {
    victim.transcript_excerpt = "caller: haan";
  }
  return { edited, seq: victim.seq };
}

// ── in-browser verification, using the engine's own verifier ───────────────

declare global {
  interface Window {
    nacl?: unknown;
    PramaanVerifier?: { verifyChain(exp: Export, nacl: unknown): Promise<Verdict> };
  }
}

let verifierLoading: Promise<void> | null = null;

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(`could not load ${src}`));
    document.head.appendChild(s);
  });
}

export async function verifyExport(exp: Export): Promise<Verdict> {
  if (!window.PramaanVerifier) {
    if (!verifierLoading) {
      verifierLoading = (async () => {
        await loadScript(enginePath("static/nacl-fast.min.js"));
        await loadScript(enginePath("static/verifier.js"));
      })();
    }
    await verifierLoading;
  }
  if (!window.PramaanVerifier || !window.nacl) throw new Error("verifier not available");
  return window.PramaanVerifier.verifyChain(exp, window.nacl);
}


/** Subscribe to the engine's live feed. Server-sent events first; if the
 *  stream cannot be held open (a buffering proxy), fall back to polling the
 *  ring buffer every two seconds. Returns an unsubscribe function. */
export function subscribeLive(pack: string, onEvent: (e: LiveEvent) => void): () => void {
  let closed = false;
  let since = 0;
  let poll: ReturnType<typeof setInterval> | null = null;
  const startPolling = () => {
    if (poll || closed) return;
    poll = setInterval(async () => {
      try {
        const r = await engine.recentEvents(pack, since);
        for (const e of r.events) { since = Math.max(since, e.seq); onEvent(e); }
        if (since === 0) since = r.latest;
      } catch { /* engine away; keep trying */ }
    }, 2000);
  };
  let es: EventSource | null = null;
  if (typeof EventSource !== "undefined") {
    const token = getToken();
    es = new EventSource(enginePath(`api/events?${q(pack)}${token ? `&token=${encodeURIComponent(token)}` : ""}`));
    const handle = (ev: MessageEvent) => {
      try { const e = JSON.parse(ev.data as string) as LiveEvent; since = Math.max(since, e.seq); onEvent(e); } catch { /* ignore */ }
    };
    for (const kind of ["session.started", "partial", "turn", "session.ended"]) es.addEventListener(kind, handle as EventListener);
    es.onerror = () => { es?.close(); es = null; startPolling(); };
  } else {
    startPolling();
  }
  return () => { closed = true; es?.close(); if (poll) clearInterval(poll); };
}


const DEV_KEY = "haanji.devanagari";
export function devanagariWanted(): boolean { try { return localStorage.getItem(DEV_KEY) === "1"; } catch { return false; } }
export function setDevanagariWanted(v: boolean): void { try { localStorage.setItem(DEV_KEY, v ? "1" : "0"); } catch { /* private mode */ } }
