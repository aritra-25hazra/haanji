/**
 * The only way the console talks to the engine. Every path goes through
 * /engine/, which Vite proxies in development, Vercel rewrites in production
 * and nginx proxies in the compose stack.
 */
import type {
  CallRow, Export, Insights, Lexicon, PackSummary, Status, Turn, Verdict,
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(enginePath(path), {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
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
