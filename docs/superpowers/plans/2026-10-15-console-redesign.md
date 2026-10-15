# Console Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the React console in the Signboard system on a light "register" surface, fed by the engine's real data, with one new engine endpoint for the lexicon.

**Architecture:** One stylesheet (`signboard.css`) holds tokens and components; `engine.ts` is the only data layer and talks to `/engine/*`; `state.tsx` holds the engine status and the chosen pack; `Common.tsx` wraps the components; each page is one file. Fixtures (`sample.ts`) are used only when the engine is unreachable. Pure functions in `engine.ts` are unit-tested with vitest; the engine endpoint with pytest; the look with the Playwright + axe script.

**Tech Stack:** React 18, TypeScript 5 (strict), Vite 5, react-router 6, recharts 2, vitest 2; FastAPI + pytest; Playwright (Python).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-10-15-console-redesign-design.md`.
- Console code never uses a raw hex colour; tokens from `signboard.css` only.
- Every network call goes through `engine.ts` and the `/engine/` prefix; no `localhost` anywhere in `console/src`.
- No emoji in the console UI; icons are the inline SVG `Icon` component.
- Controls ≥ 44 px; body 16 px; `prefers-reduced-motion` honoured; no horizontal page scroll at 390 px.
- Git: `/Library/Developer/CommandLineTools/usr/bin/git`; commits end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Build on branch `console-signboard`.
- `$PY` = `/private/tmp/claude-501/-Users-aritrahazra-Desktop-Antigravity-1-Major-Project-1-haanji/6017372c-e708-41b5-a18a-b2457744c449/scratchpad/venv/bin/python`. Engine dev server for manual checks: `cd engine && $PY -m haanji.cli serve --port 8090`; console: `cd console && npm run dev`.

---

## File map

| Path | Responsibility |
|---|---|
| `engine/haanji/server.py` | `GET /api/lexicon`. |
| `engine/tests/test_web.py` | its test. |
| `console/index.html` | fonts, title, description. |
| `console/src/signboard.css` | tokens + components (replaces `styles.css`). |
| `console/src/types.ts` | engine JSON shapes. |
| `console/src/engine.ts` | data layer + pure helpers (replaces `api.ts`, `live.ts`). |
| `console/src/engine.test.ts` | vitest for the pure helpers. |
| `console/src/sample.ts` | fallback fixtures (replaces `mock.ts`). |
| `console/src/state.tsx` | `AppProvider`, `useApp`. |
| `console/src/components/Common.tsx` | Icon, Page, Panel, Tile, Chip, OutcomeChip, Stamp, Repair, Register, Empty, useData, fmt helpers. |
| `console/src/App.tsx`, `main.tsx` | top bar, routes, provider. |
| `console/src/pages/{Dashboard,Calls,CallDetail,Ledger,Lexicon,Packs,PackStudio}.tsx` | the seven pages. |
| `engine/tests/visual_check.py` | console mode. |

---

### Task 1: Engine — `GET /api/lexicon`

**Files:**
- Modify: `engine/haanji/server.py` (import block; add the route after `/api/packs/{pack_id}/selftest`)
- Test: `engine/tests/test_web.py` (append)

**Interfaces:**
- Produces: `GET /api/lexicon?pack=<id>[&probe=<text>]` → `{pack, version, entries:[{surface, entry_type, variants, keys, weight}], probe?:{text, key, matches}}`; 404 for an unknown pack.

- [ ] **Step 1: Write the failing test**

Append to `engine/tests/test_web.py`:

```python
def test_the_lexicon_endpoint_lists_entries_and_resolves_a_probe(client):
    body = client.get("/api/lexicon?pack=dental_clinic&probe=rut%20kanal").json()
    assert body["pack"] == "dental_clinic" and body["entries"]
    assert all(e["keys"] and e["entry_type"] in ("SERVICE", "STAFF", "PLACE", "BRAND", "PHRASE")
               for e in body["entries"])
    assert "root canal" in {e["surface"] for e in body["entries"]}
    assert body["probe"]["text"] == "rut kanal" and body["probe"]["key"]
    assert "root canal" in body["probe"]["matches"]
    assert "probe" not in client.get("/api/lexicon?pack=dental_clinic").json()
    assert client.get("/api/lexicon?pack=nope").status_code == 404
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd engine && $PY -m pytest tests/test_web.py -q -k lexicon_endpoint`
Expected: FAIL (404 → `KeyError: 'pack'`).

- [ ] **Step 3: Implement**

In `engine/haanji/server.py` add to the imports (after `from .bhasha.phonetics import phrase_key`):

```python
from .bhasha.lexicon import LexEntry, TenantLexicon
```

Add after the `pack_selftest` route:

```python
@app.get("/api/lexicon")
async def lexicon(pack: str = DEFAULT_PACK, probe: str | None = None):
    """The tenant's sound-indexed vocabulary, built exactly as the pipeline
    builds it, and optionally where a heard phrase would land in it."""
    try:
        p = load_pack(pack)
    except Exception:
        raise HTTPException(404, "no such pack")
    lex = TenantLexicon.build(version=p.version, **p.lexicon_seed())
    out: dict[str, Any] = {
        "pack": pack, "version": lex.version,
        "entries": [{"surface": e.surface, "entry_type": e.entry_type.value,
                     "variants": e.variants, "keys": sorted(e.keys()),
                     "weight": round(e.weight, 2)} for e in lex.entries],
    }
    if probe and probe.strip():
        text = probe.strip()
        key = LexEntry.key_of(text.lower())
        out["probe"] = {"text": text, "key": key,
                        "matches": [c.surface for c in lex.candidates(key)]}
    return out
```

- [ ] **Step 4: Run the tests**

Run: `cd engine && $PY -m pytest -q`
Expected: `183 passed`.

- [ ] **Step 5: Commit**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G add engine/haanji/server.py engine/tests/test_web.py
$G commit -q -F - <<'MSG'
feat(engine): expose the tenant lexicon, with a probe

GET /api/lexicon returns the sound-indexed vocabulary the pipeline builds
for a pack — surface, type, variants, keys, weight — and, given ?probe=, the
key a heard phrase lands on and the entries it would match. The console's
lexicon page can now show real evidence instead of a fixture.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 2: Console foundation — stylesheet, types, data layer, state

**Files:**
- Create: `console/src/signboard.css`
- Rewrite: `console/src/types.ts`
- Create: `console/src/engine.ts`
- Create: `console/src/engine.test.ts`
- Create: `console/src/sample.ts`
- Create: `console/src/state.tsx`
- Modify: `console/index.html`
- Delete: `console/src/styles.css`, `console/src/api.ts`, `console/src/live.ts`, `console/src/mock.ts` (in Task 4, once no page imports them)

**Interfaces:**
- Produces: everything listed in spec §3; `useApp()`; the CSS classes `.topbar .nav .tools .live .main .page-title .page-sub .tiles .tile .panel .register-wrap .register .chip(.ok .warn .bad .muted) .stamp(.leaf) .repair .bubble(.agent .caller) .meta .chain .btn(.btn-primary .btn-ghost .btn-danger .btn-sm) .input .banner .empty .row .mono .muted .wordmark .dev .icon [data-reveal]`.

- [ ] **Step 1: Write the failing tests**

Create `console/src/engine.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { enginePath, fmtMs, parseReceipts, parseTurns, tamper } from "./engine";
import type { Export } from "./types";

describe("enginePath", () => {
  it("prefixes with /engine and strips leading slashes", () => {
    expect(enginePath("api/status")).toBe("/engine/api/status");
    expect(enginePath("/api/status")).toBe("/engine/api/status");
  });
});

describe("parseTurns", () => {
  it("returns normalised turns", () => {
    const turns = parseTurns(JSON.stringify([{ heard: "rut kanal", said: "Theek hai." }]));
    expect(turns).toHaveLength(1);
    expect(turns[0]).toMatchObject({ heard: "rut kanal", corrected: "rut kanal", said: "Theek hai.",
      tools: [], speculation_hits: [], guard: null, latency_ms: null, interrupted: false, corrections: [] });
  });
  it("is empty for malformed or missing json", () => {
    expect(parseTurns("not json")).toEqual([]);
    expect(parseTurns(null)).toEqual([]);
    expect(parseTurns('{"a":1}')).toEqual([]);
  });
});

describe("parseReceipts", () => {
  it("reads a list of codes and tolerates garbage", () => {
    expect(parseReceipts('["2504-7863"]')).toEqual(["2504-7863"]);
    expect(parseReceipts("")).toEqual([]);
    expect(parseReceipts("{")).toEqual([]);
  });
});

describe("fmtMs", () => {
  it("formats sub-millisecond, normal and missing latencies", () => {
    expect(fmtMs(0.4)).toBe("<1 ms");
    expect(fmtMs(22.4)).toBe("22 ms");
    expect(fmtMs(null)).toBe("—");
  });
});

describe("tamper", () => {
  it("edits one field of the middle receipt and leaves the original alone", () => {
    const exp: Export = { tenant_id: "t", algorithm: "Ed25519", public_key: "", exported_at: "",
      receipts: [1, 2, 3].map((seq) => ({ seq, action: "book_appointment", action_args: JSON.stringify({ time: "09:30" }) })) };
    const { edited, seq } = tamper(exp);
    expect(seq).toBe(2);
    expect(JSON.parse(edited.receipts[1].action_args).time).toBe("18:00");
    expect(JSON.parse(exp.receipts[1].action_args).time).toBe("09:30");
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd console && npx vitest run 2>&1 | tail -5`
Expected: FAIL — `Failed to resolve import "./engine"`.

- [ ] **Step 3: Write `types.ts`**

Replace `console/src/types.ts` with:

```ts
/** The engine's JSON, exactly as /engine/api/* returns it. */

export interface Status {
  name: string;
  version: string;
  default_pack: string;
  packs: string[];
  console_url?: string;
}

export interface Insights {
  tenant_id: string;
  generated_at: string;
  calls_total: number;
  calls_today: number;
  outcomes: Record<string, number>;
  by_hour: { hour: string; calls: number; booked: number }[];
  bookings_confirmed: number;
  revenue_booked_inr: number;
  leads_open: number;
  missed_calls: { total: number; recovered: number };
  corrections_total: number;
  speculation: { started: number; hits: number; hit_rate: number };
  cost: { ai_per_call_inr: number; receptionist_per_call_inr: number };
  insights: string[];
}

export type Outcome =
  | "BOOKED" | "FAQ_ANSWERED" | "LEAD_CAPTURED" | "HANDED_OFF" | "ABANDONED" | "IN_PROGRESS";

/** One row of the engine's `calls` table. */
export interface CallRow {
  call_id: string;
  tenant_id?: string;
  channel: string;
  phone: string | null;
  started_at: string;
  ended_at?: string | null;
  outcome: string | null;
  corrections: number;
  spec_started?: number;
  spec_hits: number;
  latency_p50: number | null;
  turns_json: string;
  receipts_json: string;
}

export interface Correction {
  from_token: string;
  to_surface: string;
  asr_confidence: number;
  ngram?: number;
  key?: string;
  to_key?: string;
}

/** One element of `turns_json`. */
export interface Turn {
  heard: string;
  corrected: string;
  said: string;
  tools: string[];
  speculation_hits: string[];
  guard: string | null;
  latency_ms: number | null;
  interrupted: boolean;
  corrections: Correction[];
}

export interface ExportReceipt {
  seq: number;
  action: string;
  action_args: string;
  short_code?: string;
  transcript_excerpt?: string;
  [key: string]: unknown;
}

export interface Export {
  tenant_id: string;
  algorithm: string;
  public_key: string;
  exported_at: string;
  receipts: ExportReceipt[];
}

export interface VerdictRow { seq: number; action: string; code: string; ok: boolean | null; reason: string | null }
export interface Verdict { ok: boolean; checked: number; firstBrokenSeq: number | null; reason: string | null; rows: VerdictRow[] }

export interface LexEntry {
  surface: string;
  entry_type: "SERVICE" | "STAFF" | "PLACE" | "BRAND" | "PHRASE";
  variants: string[];
  keys: string[];
  weight: number;
}
export interface Lexicon {
  pack: string;
  version: number;
  entries: LexEntry[];
  probe?: { text: string; key: string; matches: string[] };
}

export interface PackSummary {
  pack_id: string;
  display_name: string;
  version: number;
  language: string;
  services: number;
  staff: number;
  scenarios: number;
  issues: string[];
}
```

- [ ] **Step 4: Write `engine.ts`**

Create `console/src/engine.ts`:

```ts
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd console && npx vitest run 2>&1 | tail -5`
Expected: `5 passed` (test files 1).

- [ ] **Step 6: Write `sample.ts`**

Create `console/src/sample.ts`:

```ts
/**
 * What the console shows when the engine cannot be reached: the README's demo
 * call and the benchmark's numbers, in the engine's own shapes. Every page
 * labels it as sample data.
 */
import type { CallRow, Export, Insights, Lexicon, PackSummary, Status, Turn } from "./types";

export const SAMPLE_STATUS: Status = {
  name: "HaanJi demo server", version: "0.4.0", default_pack: "dental_clinic",
  packs: ["dental_clinic", "salon_spa", "diagnostic_lab", "coaching_institute", "clinic_kolkata"],
};

const DEMO_TURNS: Turn[] = [
  { heard: "haan ji mujhe rut kanal karwana tha", corrected: "haan ji mujhe root canal karwana tha",
    said: "Theek hai. Kis din ka time dekhun?", tools: [], speculation_hits: [], guard: null,
    latency_ms: 22, interrupted: false,
    corrections: [{ from_token: "rut kanal", to_surface: "root canal", asr_confidence: 0.32, ngram: 2 }] },
  { heard: "kal subah ka time mil jayega", corrected: "kal subah ka time mil jayega",
    said: "Kal subah saade 9 baje khaali hai, Dr Sheikh ke saath. Ya phir subah saade 10 baje. Chalega?",
    tools: ["check_availability"], speculation_hits: ["check_availability"], guard: null,
    latency_ms: 31, interrupted: false, corrections: [] },
  { heard: "haan confirm kar do", corrected: "haan confirm kar do",
    said: "Bas aapka naam aur mobile number bata dijiye.", tools: [], speculation_hits: [],
    guard: null, latency_ms: 0.4, interrupted: false, corrections: [] },
  { heard: "Vijay Sharma 9876543210", corrected: "Vijay Sharma 9876543210",
    said: "Ek baar dohra deta hoon — root canal, kal subah saade 9 baje Dr Sheikh ke saath, Vijay Sharma naam se. Confirm kar dun?",
    tools: [], speculation_hits: [], guard: null, latency_ms: 0.5, interrupted: false, corrections: [] },
  { heard: "haan confirm kar do", corrected: "haan confirm kar do",
    said: "Ho gaya. Kal subah saade 9 baje, Dr Sheikh ke saath. Confirmation code 2504-7863.",
    tools: ["book_appointment"], speculation_hits: [], guard: null, latency_ms: 301,
    interrupted: false, corrections: [] },
];

const CALLS: CallRow[] = [
  { call_id: "sample-001", channel: "PHONE", phone: "98XXXXXX10", started_at: "2026-09-07T11:04:12",
    ended_at: "2026-09-07T11:04:53", outcome: "BOOKED", corrections: 1, spec_started: 1, spec_hits: 1,
    latency_p50: 31, turns_json: JSON.stringify(DEMO_TURNS), receipts_json: JSON.stringify(["2504-7863"]) },
  { call_id: "sample-002", channel: "WHATSAPP", phone: "98XXXXXX78", started_at: "2026-09-07T10:51:02",
    ended_at: null, outcome: "FAQ_ANSWERED", corrections: 0, spec_started: 0, spec_hits: 0,
    latency_p50: 0.6, turns_json: "[]", receipts_json: "[]" },
  { call_id: "sample-003", channel: "PHONE", phone: "99XXXXXX33", started_at: "2026-09-07T10:33:47",
    ended_at: null, outcome: "LEAD_CAPTURED", corrections: 2, spec_started: 1, spec_hits: 0,
    latency_p50: 180, turns_json: "[]", receipts_json: "[]" },
  { call_id: "sample-004", channel: "PHONE", phone: null, started_at: "2026-09-07T10:12:09",
    ended_at: null, outcome: "HANDED_OFF", corrections: 0, spec_started: 0, spec_hits: 0,
    latency_p50: 0.5, turns_json: "[]", receipts_json: "[]" },
  { call_id: "sample-005", channel: "WEB", phone: "98XXXXXX02", started_at: "2026-09-07T09:58:40",
    ended_at: null, outcome: "BOOKED", corrections: 1, spec_started: 2, spec_hits: 1,
    latency_p50: 137, turns_json: "[]", receipts_json: JSON.stringify(["1F3A-90C2"]) },
];

export const sample = {
  status: SAMPLE_STATUS,

  insights(): Insights {
    return {
      tenant_id: "dental_clinic", generated_at: "2026-09-07T19:00:00",
      calls_total: 63, calls_today: 63,
      outcomes: { BOOKED: 28, FAQ_ANSWERED: 19, LEAD_CAPTURED: 7, HANDED_OFF: 6, ABANDONED: 3 },
      by_hour: [
        { hour: "09", calls: 4, booked: 2 }, { hour: "10", calls: 9, booked: 5 },
        { hour: "11", calls: 11, booked: 6 }, { hour: "12", calls: 8, booked: 3 },
        { hour: "13", calls: 3, booked: 1 }, { hour: "14", calls: 2, booked: 0 },
        { hour: "15", calls: 6, booked: 2 }, { hour: "16", calls: 7, booked: 3 },
        { hour: "17", calls: 5, booked: 3 }, { hour: "18", calls: 5, booked: 2 },
        { hour: "19", calls: 3, booked: 1 },
      ],
      bookings_confirmed: 28, revenue_booked_inr: 41200, leads_open: 7,
      missed_calls: { total: 9, recovered: 6 }, corrections_total: 41,
      speculation: { started: 110, hits: 50, hit_rate: 0.455 },
      cost: { ai_per_call_inr: 3.2, receptionist_per_call_inr: 9.2 },
      insights: [
        "Peak hour is 11:00 — 11 calls, 6 of them booked.",
        "6 of 9 missed calls were recovered on WhatsApp — ₹8,400 that would have been lost.",
        "Bhasha Bridge repaired 41 words today; the most common was 'rut kanal' → 'root canal'.",
      ],
    };
  },

  calls(): CallRow[] { return CALLS; },
  call(id: string): CallRow | null { return CALLS.find((c) => c.call_id === id) ?? null; },

  export(): Export {
    return {
      tenant_id: "dental_clinic", algorithm: "Ed25519", public_key: "", exported_at: "2026-09-07T19:00:00",
      receipts: [
        { seq: 1, action: "book_appointment", short_code: "25047863",
          action_args: JSON.stringify({ service: "root canal", date: "2026-09-08", time: "09:30", staff: "Dr Sheikh" }) },
        { seq: 2, action: "book_appointment", short_code: "1F3A90C2",
          action_args: JSON.stringify({ service: "cleaning", date: "2026-09-08", time: "16:00", staff: "Dr Mehta" }) },
      ],
    };
  },

  lexicon(): Lexicon {
    return {
      pack: "dental_clinic", version: 3,
      entries: [
        { surface: "root canal", entry_type: "SERVICE", variants: ["rut kanal"], keys: ["RTKNR"], weight: 1.25 },
        { surface: "cleaning", entry_type: "SERVICE", variants: ["klining", "teeth cleaning"], keys: ["KLNNK"], weight: 1.25 },
        { surface: "braces", entry_type: "SERVICE", variants: [], keys: ["PRSS"], weight: 1.25 },
        { surface: "Dr Sheikh", entry_type: "STAFF", variants: ["sheikh"], keys: ["TRSK"], weight: 1.1 },
        { surface: "Dr Mehta", entry_type: "STAFF", variants: [], keys: ["TRMT"], weight: 1.1 },
        { surface: "Vijay Nagar", entry_type: "PLACE", variants: ["wijay nagar"], keys: ["VJNKR"], weight: 1.0 },
        { surface: "Bhawarkuan", entry_type: "PLACE", variants: [], keys: ["PVRKN"], weight: 1.0 },
        { surface: "Smile Care", entry_type: "BRAND", variants: [], keys: ["SMLKR"], weight: 0.95 },
      ],
    };
  },

  packs(): PackSummary[] {
    return [
      { pack_id: "dental_clinic", display_name: "Dental clinic", version: 3, language: "hinglish", services: 6, staff: 2, scenarios: 6, issues: [] },
      { pack_id: "salon_spa", display_name: "Salon and spa", version: 2, language: "hinglish", services: 7, staff: 3, scenarios: 4, issues: [] },
      { pack_id: "diagnostic_lab", display_name: "Diagnostic lab", version: 2, language: "hinglish", services: 5, staff: 2, scenarios: 3, issues: [] },
      { pack_id: "coaching_institute", display_name: "Coaching institute", version: 2, language: "hinglish", services: 4, staff: 3, scenarios: 4, issues: [] },
      { pack_id: "clinic_kolkata", display_name: "Dental clinic (Kolkata, Benglish)", version: 1, language: "benglish", services: 4, staff: 2, scenarios: 3, issues: [] },
    ];
  },
};
```

- [ ] **Step 7: Write `state.tsx`**

Create `console/src/state.tsx`:

```tsx
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
```

- [ ] **Step 8: Write `signboard.css`**

Create `console/src/signboard.css`:

```css
/* HaanJi console — the Signboard system on a light surface: the board is the
   top bar, the workspace is the whitewashed wall, tables are the register. */

:root {
  --cobalt: #1B3B8C; --cobalt-deep: #102A66; --marigold: #F5B91E; --chalk: #FFF7E6;
  --ink: #14213D; --haze: #9FB3E8; --sindoor: #E2553A; --leaf: #8FD694;
  --sindoor-ink: #B8371F; --leaf-ink: #1F6B45; --marigold-ink: #8A6100;
  --paper: #FFFFFF; --rule: rgba(27, 59, 140, .14); --ink-2: rgba(20, 33, 61, .68);

  --font-display: "Bricolage Grotesque", "Arial Black", Impact, sans-serif;
  --font-dev: "Yatra One", serif;
  --font-body: "Instrument Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, Menlo, monospace;

  --t-micro: 160ms; --t-base: 240ms; --t-paint: 400ms;
  --ease-out: cubic-bezier(.2, .8, .2, 1); --ease-in: cubic-bezier(.4, 0, 1, 1);
  --r-ctl: 8px; --r-card: 12px; --maxw: 1180px;
}

*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }
body { margin: 0; min-height: 100dvh; background: var(--chalk); color: var(--ink); font: 16px/1.5 var(--font-body); -webkit-font-smoothing: antialiased; }
a { color: var(--cobalt); }
button, input, select, textarea { font: inherit; color: inherit; }
button { cursor: pointer; touch-action: manipulation; }
[hidden] { display: none !important; }
:focus-visible { outline: 3px solid var(--cobalt); outline-offset: 2px; border-radius: 4px; }
.topbar :focus-visible { outline-color: var(--marigold); }
code { font-family: var(--font-mono); font-size: .92em; background: rgba(27, 59, 140, .08); padding: 1px 6px; border-radius: 5px; }
h1, h2, h3 { margin: 0; font-family: var(--font-display); font-weight: 800; letter-spacing: -.02em; line-height: 1.1; }
p { margin: 0; }
.mono { font-family: var(--font-mono); font-weight: 500; }
.muted { color: var(--ink-2); }
.row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.icon { width: 18px; height: 18px; flex: none; vertical-align: middle; }
.icon-sm { width: 14px; height: 14px; flex: none; }

/* ── top bar: the board ─────────────────────────────────────────────── */
.topbar { position: sticky; top: 0; z-index: 10; background: var(--cobalt); color: var(--chalk); min-height: 64px; display: flex; align-items: center; gap: 18px; padding: 8px 20px; }
.wordmark { display: inline-flex; align-items: baseline; gap: 8px; font-family: var(--font-display); font-weight: 800; font-size: 22px; letter-spacing: -.02em; color: var(--marigold); text-decoration: none; white-space: nowrap; }
.wordmark .dev { font-family: var(--font-dev); font-weight: 400; font-size: 19px; color: var(--chalk); }
.nav { display: flex; gap: 2px; overflow-x: auto; scrollbar-width: none; flex: 1; min-width: 0; }
.nav::-webkit-scrollbar { display: none; }
.nav a { display: inline-flex; align-items: center; min-height: 44px; padding: 0 12px; border-radius: var(--r-ctl); color: var(--chalk); text-decoration: none; font-weight: 500; opacity: .85; white-space: nowrap; transition: background var(--t-micro), opacity var(--t-micro); }
.nav a:hover { background: rgba(255, 247, 230, .08); opacity: 1; }
.nav a.active { background: rgba(255, 247, 230, .14); opacity: 1; font-weight: 600; }
.tools { display: flex; gap: 10px; align-items: center; margin-left: auto; flex: none; }
.tools select { min-height: 40px; padding: 0 10px; border-radius: var(--r-ctl); border: 1.5px solid rgba(255, 247, 230, .35); background: var(--cobalt-deep); color: var(--chalk); max-width: 180px; }
.tools a { color: var(--chalk); text-decoration: none; display: inline-flex; align-items: center; gap: 4px; min-height: 40px; padding: 0 10px; border-radius: var(--r-ctl); font-weight: 500; opacity: .9; }
.tools a:hover { background: rgba(255, 247, 230, .08); }
.live { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; border-radius: 999px; font-size: 12px; font-weight: 700; letter-spacing: .06em; background: rgba(143, 214, 148, .18); color: var(--leaf); }
.live i { width: 7px; height: 7px; border-radius: 50%; background: var(--leaf); box-shadow: 0 0 0 3px rgba(143, 214, 148, .25); }
.live.off { background: rgba(159, 179, 232, .18); color: var(--haze); }
.live.off i { background: var(--haze); box-shadow: none; }
@media (max-width: 720px) {
  .topbar { gap: 10px; padding: 8px 12px; }
  .wordmark .dev { display: none; }
  .tools a span { display: none; }
}

/* ── page ────────────────────────────────────────────────────────────── */
.main { max-width: var(--maxw); margin: 0 auto; padding: 28px 24px 72px; }
@media (max-width: 720px) { .main { padding: 18px 14px 56px; } }
.page-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
.page-title { font-size: clamp(26px, 3.2vw, 32px); }
.page-sub { color: var(--ink-2); margin-top: 4px; max-width: 70ch; }
.banner { background: rgba(245, 185, 30, .18); border: 1px solid rgba(245, 185, 30, .5); color: var(--ink); padding: 10px 14px; border-radius: var(--r-ctl); font-size: 14px; margin-bottom: 18px; display: flex; gap: 10px; align-items: center; }
.empty { padding: 44px 20px; text-align: center; color: var(--ink-2); display: flex; flex-direction: column; align-items: center; gap: 12px; }
.loading { padding: 28px; color: var(--ink-2); }

/* ── tiles ───────────────────────────────────────────────────────────── */
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; }
.tile { background: var(--paper); border-left: 3px solid var(--marigold); border-radius: 10px; padding: 16px 18px; box-shadow: 0 1px 0 rgba(27, 59, 140, .08); }
.tile h3 { font-family: var(--font-body); font-size: 12px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--ink-2); margin-bottom: 8px; }
.tile .value { font-family: var(--font-display); font-weight: 800; font-size: 30px; letter-spacing: -.02em; color: var(--cobalt); line-height: 1; }
.tile .value.mono { font-family: var(--font-mono); font-weight: 500; font-size: 24px; }
.tile .foot { font-size: 13px; color: var(--ink-2); margin-top: 8px; }

/* ── panel ───────────────────────────────────────────────────────────── */
.panel { background: var(--paper); border: 1px solid var(--rule); border-radius: var(--r-card); margin-top: 22px; overflow: hidden; }
.panel > header { padding: 14px 18px; border-bottom: 1px solid var(--rule); display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.panel > header h2 { font-size: 16px; letter-spacing: 0; }
.panel .hint { font-size: 13px; color: var(--ink-2); }
.panel .body { padding: 18px; }

/* ── register: the signature ─────────────────────────────────────────── */
.register-wrap { overflow-x: auto; border-left: 2px solid rgba(226, 85, 58, .45); margin-left: 10px; }
.register { width: 100%; border-collapse: collapse; font-size: 14px; }
.register th { text-align: left; font-size: 12px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--ink-2); padding: 10px 14px; border-bottom: 2px solid var(--cobalt); white-space: nowrap; }
.register td { padding: 0 14px; height: 44px; border-bottom: 1px solid var(--rule); vertical-align: middle; }
.register tr:last-child td { border-bottom: 0; }
.register tbody tr.click { cursor: pointer; transition: background var(--t-micro); }
.register tbody tr.click:hover { background: rgba(27, 59, 140, .05); }
.register td.num, .register td.mono { font-family: var(--font-mono); font-weight: 500; font-size: 13px; }
.register td.right, .register th.right { text-align: right; }

/* ── chips & badges ──────────────────────────────────────────────────── */
.chip { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; border-radius: 999px; font-size: 13px; font-weight: 600; background: rgba(27, 59, 140, .1); color: var(--cobalt); white-space: nowrap; }
.chip .icon-sm { width: 14px; height: 14px; }
.chip.ok { background: rgba(31, 107, 69, .12); color: var(--leaf-ink); }
.chip.warn { background: rgba(245, 185, 30, .22); color: var(--marigold-ink); }
.chip.bad { background: rgba(184, 55, 31, .12); color: var(--sindoor-ink); }
.chip.muted { background: rgba(20, 33, 61, .08); color: var(--ink-2); }
.chip.mono { font-family: var(--font-mono); font-weight: 500; }

/* ── stamp, repair, chain ────────────────────────────────────────────── */
.stamp { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border: 2px solid var(--sindoor-ink); border-radius: 6px; background: var(--chalk); color: var(--sindoor-ink); font-family: var(--font-mono); font-weight: 500; font-size: 13px; letter-spacing: .06em; transform: rotate(-3deg); }
.stamp.leaf { border-color: var(--leaf-ink); color: var(--leaf-ink); }
.stamp.big { font-size: 17px; padding: 10px 16px; transform: rotate(-1.5deg); }
.stamp .icon { width: 16px; height: 16px; }
.repair { display: inline-flex; flex-wrap: wrap; align-items: baseline; gap: 8px; font-size: 15px; }
.repair s { position: relative; text-decoration: none; color: var(--ink-2); padding: 0 2px; }
.repair s svg { position: absolute; left: -3px; top: 0; width: calc(100% + 6px); height: 100%; overflow: visible; pointer-events: none; }
.repair s svg path { stroke: var(--cobalt); stroke-width: 2.5; fill: none; stroke-linecap: round; opacity: .75; }
.repair b { color: var(--cobalt); font-weight: 600; opacity: 0; transform: translateY(4px); transition: opacity var(--t-base) var(--ease-out) 80ms, transform var(--t-base) var(--ease-out) 80ms; }
.repair.in b { opacity: 1; transform: none; }
.repair small { font-family: var(--font-mono); font-size: 12px; color: var(--ink-2); }
.chain { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chain i { position: relative; width: 34px; height: 14px; background: var(--cobalt); border-radius: 3px; }
.chain i + i::before { content: ""; position: absolute; left: -6px; top: 6px; width: 6px; height: 2px; background: var(--cobalt); }
.chain i.empty { background: transparent; border: 2px dashed rgba(27, 59, 140, .4); }
.chain i.bad { background: var(--sindoor-ink); }
.chain i.bad::before { background: transparent; border-top: 2px dashed var(--sindoor-ink); height: 0; }

/* ── transcript ──────────────────────────────────────────────────────── */
.transcript { display: flex; flex-direction: column; gap: 10px; }
.bubble { max-width: 78%; padding: 10px 14px; border-radius: 14px; font-size: 15px; line-height: 1.45; }
.bubble.agent { align-self: flex-start; background: var(--paper); border: 1px solid var(--rule); border-bottom-left-radius: 4px; }
.bubble.caller { align-self: flex-end; background: rgba(245, 185, 30, .25); border-bottom-right-radius: 4px; }
.bubble .meta { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 8px; }
@media (max-width: 720px) { .bubble { max-width: 92%; } }

/* ── controls ────────────────────────────────────────────────────────── */
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 44px; padding: 0 18px; border-radius: var(--r-ctl); border: 1.5px solid transparent; font-weight: 600; text-decoration: none; background: transparent; color: var(--ink); transition: transform var(--t-micro) var(--ease-out), background var(--t-micro), border-color var(--t-micro), opacity var(--t-micro); }
.btn:active { transform: scale(.97); }
.btn:disabled { opacity: .45; cursor: default; transform: none; }
.btn-primary { background: var(--marigold); color: var(--cobalt); }
.btn-primary:hover:not(:disabled) { background: #FFC83D; }
.btn-ghost { border-color: rgba(27, 59, 140, .4); color: var(--cobalt); }
.btn-ghost:hover:not(:disabled) { border-color: var(--cobalt); }
.btn-danger { background: var(--sindoor-ink); color: var(--chalk); }
.btn-sm { min-height: 36px; padding: 0 12px; font-size: 14px; }
.btn .icon { width: 18px; height: 18px; }
.input { min-height: 44px; padding: 0 12px; border-radius: var(--r-ctl); border: 1.5px solid var(--rule); background: var(--paper); color: var(--ink); width: 100%; }
.input::placeholder { color: var(--ink-2); }
textarea.input { padding: 12px; font: 13px/1.55 var(--font-mono); resize: vertical; border-left: 3px solid var(--cobalt); }
.field { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--ink-2); }

/* ── outcomes bar ────────────────────────────────────────────────────── */
.obar { display: flex; height: 18px; border-radius: 9px; overflow: hidden; background: rgba(27, 59, 140, .08); }
.obar i { display: block; height: 100%; }
.obar .BOOKED { background: var(--leaf-ink); } .obar .FAQ_ANSWERED { background: var(--cobalt); }
.obar .LEAD_CAPTURED { background: var(--marigold); } .obar .HANDED_OFF { background: var(--sindoor-ink); }
.obar .ABANDONED, .obar .IN_PROGRESS { background: rgba(20, 33, 61, .3); }
.legend { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 10px; font-size: 13px; color: var(--ink-2); }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: middle; }

/* ── reveal ──────────────────────────────────────────────────────────── */
[data-reveal] { opacity: 0; transform: translateY(8px); animation: reveal var(--t-base) var(--ease-out) forwards; animation-delay: calc(var(--i, 0) * 30ms); }
@keyframes reveal { to { opacity: 1; transform: none; } }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 1ms !important; transition-duration: 1ms !important; }
  [data-reveal] { opacity: 1; transform: none; animation: none; }
  .repair b { opacity: 1; transform: none; }
}
```

- [ ] **Step 9: `index.html`**

Replace `console/index.html` with:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#1B3B8C" />
    <meta name="description" content="HaanJi owner console — calls, receipts, vocabulary and packs." />
    <title>HaanJi Console</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,800&family=Yatra+One&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 10: Commit the foundation**

The build will not pass yet (pages still import the old modules) — that is expected; the foundation and its unit tests are committable on their own.

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
cd console && npx vitest run 2>&1 | tail -3 && cd ..
$G add console/src/signboard.css console/src/types.ts console/src/engine.ts console/src/engine.test.ts console/src/sample.ts console/src/state.tsx console/index.html
$G commit -q -F - <<'MSG'
feat(console): Signboard foundation — tokens, engine data layer, state

The console's own stylesheet in the Signboard system on a light surface
(the board is the top bar, the workspace is the wall, tables are the
register); a single data layer that talks to /engine/* and nothing else,
with the pure parts unit-tested; engine-shaped sample data for when the
engine is unreachable; and an app state that holds the engine status and
the chosen pack.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 3: Components and the shell

**Files:**
- Rewrite: `console/src/components/Common.tsx`
- Rewrite: `console/src/App.tsx`, `console/src/main.tsx`

**Interfaces:**
- Produces: `Icon({name, size?})` with names `phone mic bolt shield lock arrow check x chevron external refresh`; `Page({title, sub?, actions?, children})`; `Panel({title, hint?, actions?, children})`; `Tile({label, value, foot?, mono?})` (numbers count up); `Chip({kind?, mono?, children})` kind ∈ `ok|warn|bad|muted`; `OutcomeChip({outcome})`; `Stamp({tone?, big?, children})` tone ∈ `red|leaf`; `Repair({c})`; `Register({head, children})`; `Empty({children})`; `Loading()`; `useData(load, deps)` → `{data, loading, error, reload}`; `useCountUp(n)`; `fmtTime(iso)`, `fmtInr(n)`, `fmtDate(iso)`.

- [ ] **Step 1: Write `Common.tsx`**

Replace `console/src/components/Common.tsx` with:

```tsx
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useApp } from "../state";

const REDUCED = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

// ── icons: one family, inline SVG ──────────────────────────────────────────
const PATHS: Record<string, string> = {
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6.2 6.2l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
  mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/>',
  bolt: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  arrow: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  chevron: '<polyline points="6 9 12 15 18 9"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.5 15a9 9 0 1 1-2.1-9.4L23 10"/>',
};

export function Icon({ name, small = false }: { name: keyof typeof PATHS | string; small?: boolean }) {
  return (
    <svg className={small ? "icon-sm" : "icon"} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: PATHS[name] ?? "" }} />
  );
}

// ── layout ─────────────────────────────────────────────────────────────────
export function Page({ title, sub, actions, children }:
  { title: string; sub?: string; actions?: ReactNode; children: ReactNode }) {
  const { checked, online } = useApp();
  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">{title}</h1>
          {sub && <p className="page-sub">{sub}</p>}
        </div>
        {actions && <div className="row">{actions}</div>}
      </div>
      {checked && !online && (
        <div className="banner" role="status">
          <Icon name="refresh" small />
          Engine se connect nahi ho pa raha — sample data dikha raha hoon. Thodi der mein dobara try karo.
        </div>
      )}
      {children}
    </>
  );
}

export function Panel({ title, hint, actions, children }:
  { title: string; hint?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel">
      <header>
        <h2>{title}</h2>
        <div className="row">{hint && <span className="hint">{hint}</span>}{actions}</div>
      </header>
      {children}
    </section>
  );
}

export function useCountUp(target: number, ms = 400): number {
  const [n, setN] = useState(REDUCED ? target : 0);
  const from = useRef(0);
  useEffect(() => {
    if (REDUCED) { setN(target); return; }
    const start = performance.now(), a = from.current, b = target;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / ms), e = 1 - Math.pow(1 - p, 3);
      setN(a + (b - a) * e);
      if (p < 1) raf = requestAnimationFrame(tick); else from.current = b;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return n;
}

function CountUp({ value, decimals }: { value: number; decimals: number }) {
  const n = useCountUp(value);
  return <>{n.toLocaleString("en-IN", { maximumFractionDigits: decimals, minimumFractionDigits: decimals })}</>;
}

export function Tile({ label, value, foot, mono = false, decimals = 0, prefix = "", suffix = "", index = 0 }:
  { label: string; value: ReactNode | number; foot?: string; mono?: boolean; decimals?: number; prefix?: string; suffix?: string; index?: number }) {
  return (
    <div className="tile" data-reveal style={{ "--i": index } as React.CSSProperties}>
      <h3>{label}</h3>
      <div className={"value" + (mono ? " mono" : "")}>
        {typeof value === "number" ? <>{prefix}<CountUp value={value} decimals={decimals} />{suffix}</> : value}
      </div>
      {foot && <div className="foot">{foot}</div>}
    </div>
  );
}

export function Chip({ kind, mono = false, children }:
  { kind?: "ok" | "warn" | "bad" | "muted"; mono?: boolean; children: ReactNode }) {
  return <span className={"chip" + (kind ? ` ${kind}` : "") + (mono ? " mono" : "")}>{children}</span>;
}

const OUTCOME_KIND: Record<string, "ok" | "warn" | "bad" | "muted" | undefined> = {
  BOOKED: "ok", FAQ_ANSWERED: undefined, LEAD_CAPTURED: "warn", HANDED_OFF: "bad", ABANDONED: "muted", IN_PROGRESS: "muted",
};
export function OutcomeChip({ outcome }: { outcome: string | null }) {
  const o = outcome || "IN_PROGRESS";
  return <Chip kind={OUTCOME_KIND[o]}>{o.replace(/_/g, " ").toLowerCase()}</Chip>;
}

export function Stamp({ tone = "red", big = false, children }:
  { tone?: "red" | "leaf"; big?: boolean; children: ReactNode }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || REDUCED) return;
    const rot = big ? "rotate(-1.5deg)" : "rotate(-3deg)";
    const a = el.animate([
      { transform: `${rot} scale(1.35)`, opacity: 0 }, { opacity: 1, offset: .6 },
      { opacity: .8, offset: .7 }, { transform: `${rot} scale(1)`, opacity: 1 },
    ], { duration: 400, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" });
    return () => a.cancel();
  }, [big, children]);
  return <span ref={ref} className={"stamp" + (tone === "leaf" ? " leaf" : "") + (big ? " big" : "")}>{children}</span>;
}

export function Repair({ c }: { c: { from_token: string; to_surface: string; asr_confidence?: number } }) {
  const ref = useRef<HTMLElement>(null);
  const [painted, setPainted] = useState(REDUCED);
  useEffect(() => {
    const s = ref.current;
    if (!s) return;
    const path = s.querySelector("path");
    if (!path || REDUCED) { setPainted(true); return; }
    const len = 120;
    path.style.strokeDasharray = String(len);
    const a = path.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }],
      { duration: 400, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" });
    setPainted(true);
    return () => a.cancel();
  }, [c.from_token]);
  return (
    <span className={"repair" + (painted ? " in" : "")}>
      <s ref={ref} aria-label={`suna: ${c.from_token}`}>
        {c.from_token}
        <svg viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true"><path d="M1 6 Q 25 3, 50 6 T 99 5" /></svg>
      </s>
      <b aria-label={`padha: ${c.to_surface}`}>{c.to_surface}</b>
      {c.asr_confidence != null && <small>{c.asr_confidence.toFixed(2)}</small>}
    </span>
  );
}

export function Register({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <div className="register-wrap">
      <table className="register">
        <thead><tr>{head}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) { return <div className="empty">{children}</div>; }
export function Loading() { return <div className="loading">Loading…</div>; }

export function useData<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: s.data === undefined }));
    load().then((data) => alive && setState({ data, loading: false }))
      .catch((e: Error) => alive && setState((s) => ({ ...s, error: e.message, loading: false })));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso.slice(11, 16) : d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
}
export function fmtDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso.slice(0, 10) : d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
export function fmtInr(n: number): string { return "₹" + Math.round(n).toLocaleString("en-IN"); }
```

- [ ] **Step 2: Write `App.tsx` and `main.tsx`**

Replace `console/src/App.tsx`:

```tsx
import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Icon } from "./components/Common";
import { useApp } from "./state";
import Dashboard from "./pages/Dashboard";
import Calls from "./pages/Calls";
import CallDetail from "./pages/CallDetail";
import Ledger from "./pages/Ledger";
import Lexicon from "./pages/Lexicon";
import Packs from "./pages/Packs";
import PackStudio from "./pages/PackStudio";

const LINKS: [string, string][] = [
  ["/dashboard", "Aaj"], ["/calls", "Calls"], ["/ledger", "Pramaan"],
  ["/lexicon", "Bhasha"], ["/packs", "Packs"], ["/studio", "Studio"],
];

export default function App() {
  const { online, checked, pack, packs, setPack } = useApp();
  return (
    <>
      <header className="topbar">
        <Link className="wordmark" to="/dashboard">HaanJi <span className="dev">हाँजी</span></Link>
        <nav className="nav" aria-label="Main">
          {LINKS.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : undefined)}>{label}</NavLink>
          ))}
        </nav>
        <div className="tools">
          <label className="field" style={{ gap: 0 }}>
            <span className="muted" style={{ fontSize: 0, lineHeight: 0 }}>Pack</span>
            <select aria-label="Pack" value={pack} onChange={(e) => setPack(e.target.value)}>
              {packs.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <span className={"live" + (online ? "" : " off")} title={online ? "engine se live" : checked ? "sample data" : "checking"}>
            <i />{online ? "LIVE" : checked ? "SAMPLE" : "…"}
          </span>
          <a href="/engine/talk" target="_blank" rel="noopener noreferrer"><span>Talk</span><Icon name="external" small /></a>
        </div>
      </header>
      <main className="main" id="main">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/calls" element={<Calls />} />
          <Route path="/calls/:id" element={<CallDetail />} />
          <Route path="/ledger" element={<Ledger />} />
          <Route path="/lexicon" element={<Lexicon />} />
          <Route path="/packs" element={<Packs />} />
          <Route path="/studio" element={<PackStudio />} />
        </Routes>
      </main>
    </>
  );
}
```

Replace `console/src/main.tsx`:

```tsx
import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AppProvider } from "./state";
import "./signboard.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppProvider>
        <App />
      </AppProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
```

- [ ] **Step 3: Commit** (the build still fails until the pages are rewritten in Task 4)

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G add console/src/components/Common.tsx console/src/App.tsx console/src/main.tsx
$G commit -q -F - <<'MSG'
feat(console): the shell — top bar, pack chooser, live chip — and the components

Page, Panel, Tile (numbers count up), Chip and outcome chips, Stamp, the
painted Repair, Register, Empty, Loading, useData and the formatters, with
one inline SVG icon family. The top bar carries the wordmark, the six
pages, a global pack chooser and a LIVE/SAMPLE chip.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 4: The seven pages

**Files:**
- Rewrite: `console/src/pages/Dashboard.tsx`, `Calls.tsx`, `CallDetail.tsx`, `Ledger.tsx`, `Lexicon.tsx`, `Packs.tsx`, `PackStudio.tsx`
- Delete: `console/src/api.ts`, `live.ts`, `mock.ts`, `styles.css`

**Interfaces:**
- Consumes: everything from Tasks 2–3.

- [ ] **Step 1: `Dashboard.tsx`**

```tsx
import { useEffect } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { engine } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Loading, Page, Panel, Tile, fmtInr, fmtTime, useData } from "../components/Common";

const ORDER = ["BOOKED", "FAQ_ANSWERED", "LEAD_CAPTURED", "HANDED_OFF", "ABANDONED", "IN_PROGRESS"];

export default function Dashboard() {
  const { pack, online } = useApp();
  const { data, loading, error, reload } = useData(
    () => (online ? engine.insights(pack) : Promise.resolve(sample.insights())), [pack, online]);
  useEffect(() => {
    if (!online) return;
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
  }, [online, reload]);

  if (loading && !data) return <Loading />;
  if (!data) return <Page title="Aaj"><div className="empty">Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></div></Page>;

  const total = Object.values(data.outcomes).reduce((a, b) => a + b, 0) || 1;
  const peak = data.by_hour.reduce((m, h) => (h.calls > m.calls ? h : m), { hour: "—", calls: 0, booked: 0 });

  return (
    <Page title="Aaj" sub={`${pack.replace(/_/g, " ")} — har call jo agent ne uthayi, aur usse kya nikla.`}>
      <div className="tiles">
        <Tile index={0} label="Calls aaj" value={data.calls_today} foot={`${data.calls_total} kul`} />
        <Tile index={1} label="Bookings" value={data.bookings_confirmed} foot={`${fmtInr(data.revenue_booked_inr)} ki`} />
        <Tile index={2} label="Missed calls wapas" value={`${data.missed_calls.recovered}/${data.missed_calls.total}`} foot="WhatsApp se" />
        <Tile index={3} label="₹ per call" value={data.cost.ai_per_call_inr} decimals={2} prefix="₹" mono foot={`receptionist ₹${data.cost.receptionist_per_call_inr.toFixed(2)}`} />
        <Tile index={4} label="Shabd sudhaare" value={data.corrections_total} foot="Bhasha Bridge" />
        <Tile index={5} label="Speculation hits" value={Math.round(data.speculation.hit_rate * 100)} suffix="%" foot={`${data.speculation.hits} of ${data.speculation.started} tool calls`} />
      </div>

      <Panel title="Din bhar ki calls" hint={`peak ${peak.hour}:00 — ${peak.calls} calls · booked marigold mein`}>
        <div className="body" style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.by_hour} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid stroke="rgba(27,59,140,.14)" vertical={false} />
              <XAxis dataKey="hour" tickLine={false} axisLine={{ stroke: "rgba(27,59,140,.3)" }} tick={{ fontSize: 12, fill: "rgba(20,33,61,.68)" }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "rgba(20,33,61,.68)" }} allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(27,59,140,.06)" }} contentStyle={{ borderRadius: 8, border: "1px solid rgba(27,59,140,.14)", fontSize: 13 }} />
              <Bar dataKey="calls" name="calls" fill="#1B3B8C" radius={[3, 3, 0, 0]} />
              <Bar dataKey="booked" name="booked" fill="#F5B91E" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <Panel title="Calls kaise khatam huin" hint={`${total} calls`}>
        <div className="body">
          <div className="obar" role="img" aria-label={ORDER.filter((o) => data.outcomes[o]).map((o) => `${o.toLowerCase()} ${data.outcomes[o]}`).join(", ")}>
            {ORDER.filter((o) => data.outcomes[o]).map((o) => <i key={o} className={o} style={{ width: `${(data.outcomes[o] / total) * 100}%` }} />)}
          </div>
          <div className="legend">
            {ORDER.filter((o) => data.outcomes[o]).map((o) => (
              <span key={o}><i className={`obar-${o}`} style={{ background: `var(--${o === "BOOKED" ? "leaf-ink" : o === "FAQ_ANSWERED" ? "cobalt" : o === "LEAD_CAPTURED" ? "marigold" : o === "HANDED_OFF" ? "sindoor-ink" : "ink-2"})` }} />{o.replace(/_/g, " ").toLowerCase()} · {data.outcomes[o]}</span>
            ))}
          </div>
        </div>
      </Panel>

      <Panel title="Engine ne kya dekha" hint={`${fmtTime(data.generated_at)} pe bana${online ? " · har 5 s refresh" : ""}`}>
        <div className="body">
          {data.insights.length === 0 && <p className="muted">Abhi kuch kehne layak nahi — kuch calls hone do.</p>}
          {data.insights.map((line, i) => <p key={i} data-reveal style={{ "--i": i, margin: "6px 0" } as React.CSSProperties}>• {line}</p>)}
        </div>
      </Panel>
    </Page>
  );
}
```

Note: the recharts `fill` props are the only place a hex appears in the console — recharts cannot read CSS variables from an attribute. They are the system's cobalt and marigold.

- [ ] **Step 2: `Calls.tsx`**

```tsx
import { useNavigate } from "react-router-dom";
import { engine, fmtMs } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Empty, Icon, Loading, OutcomeChip, Page, Panel, Register, fmtDate, fmtTime, useData } from "../components/Common";

export default function Calls() {
  const { pack, online } = useApp();
  const nav = useNavigate();
  const { data, loading, error, reload } = useData(
    () => (online ? engine.calls(pack).then((r) => r.conversations) : Promise.resolve(sample.calls())), [pack, online]);

  if (loading && !data) return <Loading />;
  if (!data) return <Page title="Calls"><Empty>Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty></Page>;

  return (
    <Page title="Calls" sub="Nayi pehle. Transcript aur receipt ke liye row kholo.">
      <Panel title={online ? "Engine ki calls" : "Sample calls"} hint={`${data.length} calls · ${pack.replace(/_/g, " ")}`}>
        {data.length === 0 ? (
          <Empty>
            <p>Abhi koi call nahi.</p>
            <a className="btn btn-primary" href="/engine/talk" target="_blank" rel="noopener noreferrer">/talk pe ek call karke dekho <Icon name="external" small /></a>
          </Empty>
        ) : (
          <Register head={<><th>Kab</th><th>Channel</th><th>Caller</th><th>Outcome</th><th className="right">Repairs</th><th className="right">Spec hits</th><th className="right">Latency p50</th></>}>
            {data.map((c, i) => (
              <tr key={c.call_id} className="click" data-reveal style={{ "--i": i } as React.CSSProperties}
                  onClick={() => nav(`/calls/${c.call_id}`)} tabIndex={0}
                  onKeyDown={(e) => { if (e.key === "Enter") nav(`/calls/${c.call_id}`); }}>
                <td className="mono">{fmtDate(c.started_at)} {fmtTime(c.started_at)}</td>
                <td>{c.channel.toLowerCase()}</td>
                <td className="mono">{c.phone ?? "—"}</td>
                <td><OutcomeChip outcome={c.outcome} /></td>
                <td className="num right">{c.corrections}</td>
                <td className="num right">{c.spec_hits}{c.spec_started != null ? `/${c.spec_started}` : ""}</td>
                <td className="num right">{fmtMs(c.latency_p50)}</td>
              </tr>
            ))}
          </Register>
        )}
      </Panel>
    </Page>
  );
}
```

- [ ] **Step 3: `CallDetail.tsx`**

```tsx
import { Link, useParams } from "react-router-dom";
import { engine, fmtMs, parseReceipts, parseTurns } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Chip, Empty, Icon, Loading, OutcomeChip, Page, Panel, Repair, Stamp, Tile, fmtDate, fmtTime, useData } from "../components/Common";
import type { CallRow } from "../types";

export default function CallDetail() {
  const { id = "" } = useParams();
  const { pack, online } = useApp();
  const { data, loading, error } = useData<CallRow | null>(
    () => (online ? engine.call(pack, id) : Promise.resolve(sample.call(id))), [pack, online, id]);

  if (loading && !data) return <Loading />;
  if (!data) return <Page title="Call"><Empty>Ye call nahi mili{error ? ` — ${error}` : ""}. <Link to="/calls">Calls pe wapas</Link></Empty></Page>;

  const turns = parseTurns(data.turns_json);
  const receipts = parseReceipts(data.receipts_json);
  const repairs = turns.reduce((n, t) => n + t.corrections.length, 0);

  return (
    <Page title="Call" sub={`${data.channel.toLowerCase()} · ${data.phone ?? "number nahi"} · ${fmtDate(data.started_at)} ${fmtTime(data.started_at)}`}
          actions={<Link className="btn btn-ghost btn-sm" to="/calls">Saari calls</Link>}>
      <div className="tiles">
        <Tile index={0} label="Outcome" value={<OutcomeChip outcome={data.outcome} />} />
        <Tile index={1} label="Shabd sudhaare" value={repairs} foot="tenant ki apni vocabulary se" />
        <Tile index={2} label="Receipt" value={receipts.length ? <Stamp><Icon name="lock" small />{receipts[receipts.length - 1]}</Stamp> : "—"} foot={receipts.length ? "signed aur chained" : "kuch likha nahi gaya"} />
      </div>

      <Panel title="Transcript" hint="jo suna gaya, aur agent ne kya padha aur bola">
        <div className="body transcript">
          {turns.length === 0 && <p className="muted">Is call ke turns record nahi hue.</p>}
          {turns.map((t, i) => (
            <div key={i} style={{ display: "contents" }}>
              <div className="bubble caller" data-reveal style={{ "--i": i * 2 } as React.CSSProperties}>
                {t.heard}
                {t.corrections.length > 0 && <div className="meta">{t.corrections.map((c, j) => <Repair key={j} c={c} />)}</div>}
              </div>
              <div className="bubble agent" data-reveal style={{ "--i": i * 2 + 1 } as React.CSSProperties}>
                {t.said}
                <div className="meta">
                  {t.tools.map((tool) => {
                    const hit = t.speculation_hits.includes(tool);
                    return <Chip key={tool} kind={hit ? "ok" : undefined}>{hit && <Icon name="bolt" small />}{tool}{hit ? " · speculated" : ""}</Chip>;
                  })}
                  {t.guard && <Chip kind="bad"><Icon name="shield" small />guardrail: {t.guard}</Chip>}
                  {t.interrupted && <Chip kind="muted">caller ne beech mein toka</Chip>}
                  <span className="mono muted" style={{ fontSize: 13 }}>{fmtMs(t.latency_ms)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      {receipts.length > 0 && (
        <Panel title="Pramaan receipts" hint="har ek Ed25519 signed, pichhli se chained" actions={<Link className="btn btn-ghost btn-sm" to="/ledger">Verify karo <Icon name="arrow" small /></Link>}>
          <div className="body row">
            {receipts.map((code) => <Stamp key={code}><Icon name="lock" small />RECEIPT {code}</Stamp>)}
          </div>
        </Panel>
      )}
    </Page>
  );
}
```

- [ ] **Step 4: `Ledger.tsx`**

```tsx
import { useCallback, useState } from "react";
import { engine, tamper, verifyExport } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Chip, Empty, Icon, Loading, Page, Panel, Register, Stamp, Tile, useData } from "../components/Common";
import type { Export, Verdict } from "../types";

export default function Ledger() {
  const { pack, online } = useApp();
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const run = useCallback(async (exp: Export, note: string) => {
    setBusy(true); setProblem(null);
    try { setVerdict(await verifyExport(exp)); setLabel(note); }
    catch (e) { setProblem((e as Error).message); }
    finally { setBusy(false); }
  }, []);

  const { data, loading, error, reload } = useData<Export>(async () => {
    if (!online) { setVerdict(null); return sample.export(); }
    const exp = await engine.export(pack);
    await run(exp, "engine ke export pe, abhi");
    return exp;
  }, [pack, online]);

  if (loading && !data) return <Loading />;
  if (!data) return <Page title="Pramaan"><Empty>Export load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty></Page>;

  const firstBroken = verdict && !verdict.ok ? verdict.firstBrokenSeq : null;
  const rows = verdict ? verdict.rows : data.receipts.map((r) => ({ seq: r.seq, action: r.action, code: String(r.short_code ?? ""), ok: null, reason: null }));

  return (
    <Page title="Pramaan ledger" sub="Har booking ek signed, chained receipt — aur ye page usse aapke browser mein dobara jaanchta hai, server pe bharosa kiye bina."
          actions={online ? <>
            <button className="btn btn-ghost btn-sm" disabled={busy} onClick={reload}><Icon name="refresh" small />Dobara verify karo</button>
            <button className="btn btn-danger btn-sm" disabled={busy || !data.receipts.length} onClick={() => { const t = tamper(data); void run(t.edited, `receipt seq ${t.seq} ko yahin edit karne ke baad`); }}><Icon name="x" small />Ek field chhedo aur dobara check karo</button>
          </> : undefined}>
      <div className="tiles">
        <Tile index={0} label="Receipts" value={data.receipts.length} foot={`tenant ${data.tenant_id}`} />
        <Tile index={1} label="Chain" value={verdict ? (verdict.ok ? <Stamp tone="leaf"><Icon name="check" small />VALID</Stamp> : <Stamp><Icon name="x" small />BROKEN</Stamp>) : <span className="muted" style={{ fontSize: 16 }}>{online ? "jaanch raha hoon…" : "live engine chahiye"}</span>}
              foot={verdict ? (verdict.ok ? `${verdict.checked} receipts, har hash aur signature dobara bana` : `seq ${verdict.firstBrokenSeq}: ${verdict.reason}`) : (online ? "" : "sample receipts verify nahi ho sakte")} />
        <Tile index={2} label="Bina confirm writes" value={0} foot="ledger inhe accept hi nahi karta" />
      </div>

      {problem && <div className="banner" role="status"><Icon name="x" small />Verify nahi ho paya: {problem}</div>}

      {verdict && (
        <Panel title="Verdict" hint={label}>
          <div className="body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>{verdict.ok
              ? <Stamp tone="leaf" big><Icon name="check" />VALID · {verdict.checked} receipts · chain intact</Stamp>
              : <Stamp big><Icon name="x" />BROKEN at seq {verdict.firstBrokenSeq} · {verdict.reason}</Stamp>}</div>
            <div className="chain" aria-hidden="true">
              {rows.map((r) => <i key={r.seq} className={firstBroken != null && r.seq >= firstBroken ? "bad" : undefined} />)}
              <i className="empty" />
            </div>
            <div className="mono muted" style={{ fontSize: 12, wordBreak: "break-all" }}>public key (Ed25519): {data.public_key || "—"}</div>
            {!online && null}
            <p className="muted" style={{ fontSize: 13 }}>"Chhedo" wala button sirf aapke browser ki copy badalta hai — server pe kuch nahi jaata.</p>
          </div>
        </Panel>
      )}

      <Panel title="Receipts" hint={rows.length ? `${rows.length} entries` : "abhi koi nahi"}>
        {rows.length === 0 ? (
          <Empty><p>Export mein koi receipt nahi.</p><a className="btn btn-primary" href="/engine/talk" target="_blank" rel="noopener noreferrer">Pehle ek booking karo <Icon name="external" small /></a></Empty>
        ) : (
          <Register head={<><th>Seq</th><th>Action</th><th>Code</th><th>Verdict</th><th>Reason</th></>}>
            {rows.map((r, i) => (
              <tr key={r.seq} data-reveal style={{ "--i": i } as React.CSSProperties}>
                <td className="num">{r.seq}</td>
                <td>{r.action}</td>
                <td className="mono">{r.code ? `${r.code.slice(0, 4)}-${r.code.slice(4, 8)}` : "—"}</td>
                <td>{r.ok === true ? <Chip kind="ok"><Icon name="check" small />verified</Chip> : r.ok === false ? <Chip kind="bad"><Icon name="x" small />BROKEN</Chip> : <Chip kind="muted">{online ? "skipped" : "sample"}</Chip>}</td>
                <td className="muted">{r.reason ?? (r.ok === true ? "hash + link + signature, teeno dobara bane" : "")}</td>
              </tr>
            ))}
          </Register>
        )}
      </Panel>
    </Page>
  );
}
```

- [ ] **Step 5: `Lexicon.tsx`**

```tsx
import { useEffect, useState } from "react";
import { engine } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Chip, Empty, Icon, Loading, Page, Panel, Register, useData } from "../components/Common";

const KIND: Record<string, "ok" | "warn" | "bad" | "muted" | undefined> = { SERVICE: "ok", STAFF: undefined, PLACE: "warn", BRAND: "muted", PHRASE: "muted" };

export default function Lexicon() {
  const { pack, online } = useApp();
  const [probe, setProbe] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(probe.trim()), 300); return () => clearTimeout(t); }, [probe]);

  const { data, loading, error, reload } = useData(
    () => (online ? engine.lexicon(pack, debounced || undefined) : Promise.resolve(sample.lexicon())), [pack, online, debounced]);

  if (loading && !data) return <Loading />;
  if (!data) return <Page title="Bhasha lexicon"><Empty>Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty></Page>;

  return (
    <Page title="Bhasha lexicon" sub="Is business ke apne shabd, awaaz ke hisaab se indexed. Catalogue se khud banta hai — ye list koi type nahi karta.">
      <Panel title="Jo suna gaya, wo likho" hint={online ? "engine batayega ye awaaz kahan land karti hai" : "live engine chahiye"}>
        <div className="body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <input className="input" value={probe} onChange={(e) => setProbe(e.target.value)} disabled={!online}
                 placeholder='jaise "rut kanal" ya "sheikh"' aria-label="Suna hua phrase" style={{ maxWidth: 420 }} />
          {data.probe && (
            <div className="row" style={{ fontSize: 15 }}>
              <span>"{data.probe.text}"</span><Icon name="arrow" small />
              <Chip mono>{data.probe.key || "—"}</Chip><Icon name="arrow" small />
              {data.probe.matches.length
                ? data.probe.matches.map((m) => <Chip key={m} kind="ok"><Icon name="check" small />{m}</Chip>)
                : <Chip kind="muted">koi entry is awaaz pe nahi</Chip>}
            </div>
          )}
        </div>
      </Panel>

      <Panel title="Vocabulary" hint={`${data.entries.length} entries · v${data.version}`}>
        <Register head={<><th>Shabd</th><th>Kind</th><th>Aise bhi suna</th><th>Sound key</th><th className="right">Weight</th></>}>
          {data.entries.map((e, i) => (
            <tr key={e.surface + i} data-reveal style={{ "--i": Math.min(i, 20) } as React.CSSProperties}>
              <td><strong>{e.surface}</strong></td>
              <td><Chip kind={KIND[e.entry_type]}>{e.entry_type.toLowerCase()}</Chip></td>
              <td className="muted">{e.variants.join(", ") || "—"}</td>
              <td className="mono">{e.keys.join(" · ")}</td>
              <td className="num right">{e.weight.toFixed(2)}</td>
            </tr>
          ))}
        </Register>
      </Panel>

      <Panel title="Ek repair kab hota hai">
        <div className="body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p>Ek shabd tabhi badla jaata hai jab do alag-alag cheezein ek saath sach hon: recogniser us shabd pe <strong>sure nahi</strong> tha (confidence 0.85 se kam), <em>aur</em> uski sound key is list ki kisi entry se <strong>bilkul match</strong> karti hai, chhoti si spelling doori ke andar. Dono mein se koi ek akela galat corrections deta hai — aur jo layer achhe transcript ko bigaade, wo na hone se buri hai.</p>
          <p className="muted">Caller ne abhi-abhi jo naam bataya, usse kabhi nahi chheda jaata, chahe wo kaisa bhi sune.</p>
        </div>
      </Panel>
    </Page>
  );
}
```

- [ ] **Step 6: `Packs.tsx`**

```tsx
import { engine } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Chip, Empty, Loading, Page, Panel, Register, useData } from "../components/Common";

export default function Packs() {
  const { pack, online, setPack } = useApp();
  const { data, loading, error, reload } = useData(
    () => (online ? engine.packs().then((r) => r.packs) : Promise.resolve(sample.packs())), [online]);

  if (loading && !data) return <Loading />;
  if (!data) return <Page title="Packs"><Empty>Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty></Page>;

  return (
    <Page title="Vertical packs" sub="Ek file batati hai agent kya jaanta hai, kya mana karta hai, aur kaise bolta hai.">
      <Panel title="Installed" hint={`${data.length} packs`}>
        <Register head={<><th>Pack</th><th>Language</th><th className="right">Services</th><th className="right">Staff</th><th className="right">Scenarios</th><th>Health</th><th></th></>}>
          {data.map((p, i) => (
            <tr key={p.pack_id} data-reveal style={{ "--i": i } as React.CSSProperties}>
              <td><strong>{p.display_name}</strong> <span className="muted mono" style={{ fontSize: 12 }}>v{p.version}</span></td>
              <td>{p.language}</td>
              <td className="num right">{p.services}</td>
              <td className="num right">{p.staff}</td>
              <td className="num right">{p.scenarios}</td>
              <td>{p.issues.length === 0 ? <Chip kind="ok">valid</Chip> : <Chip kind="bad">{p.issues.length} issues</Chip>}</td>
              <td className="right">{p.pack_id === pack ? <Chip kind="warn">in use</Chip> : <button className="btn btn-ghost btn-sm" onClick={() => setPack(p.pack_id)}>Use</button>}</td>
            </tr>
          ))}
        </Register>
      </Panel>

      <Panel title="Ek pack mein kya hota hai">
        <div className="body">
          <dl style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: "8px 16px", margin: 0 }}>
            <dt className="muted">Catalogue</dt><dd style={{ margin: 0 }}>services, kitna time, daam, kaun karta hai</dd>
            <dt className="muted">Hours</dt><dd style={{ margin: 0 }}>din, khulne-band hone ka time, breaks</dd>
            <dt className="muted">Persona</dt><dd style={{ margin: 0 }}>greeting, tone, ek baar mein kitna bolna</dd>
            <dt className="muted">Guardrails</dt><dd style={{ margin: 0 }}>kya seedha mana karna, kya insaan ko dena</dd>
            <dt className="muted">Vocabulary</dt><dd style={{ margin: 0 }}>sound-index ke seed shabd — ilaake, brands, aam phrases</dd>
            <dt className="muted">Knowledge</dt><dd style={{ margin: 0 }}>jo sawaal log sach mein poochte hain, aur jawab</dd>
            <dt className="muted">Scenarios</dt><dd style={{ margin: 0 }}>wo calls jo pack ko ship hone se pehle paas karni hain</dd>
          </dl>
        </div>
      </Panel>
    </Page>
  );
}
```

- [ ] **Step 7: `PackStudio.tsx`**

```tsx
import { useEffect, useState } from "react";
import { engine } from "../engine";
import { useApp } from "../state";
import { Chip, Empty, Icon, Page, Panel, Register } from "../components/Common";
import type { PackSummary } from "../types";

export default function PackStudio() {
  const { online } = useApp();
  const [packs, setPacks] = useState<PackSummary[] | null>(null);
  const [current, setCurrent] = useState("");
  const [yamlText, setYamlText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [messages, setMessages] = useState<{ kind: "ok" | "bad"; text: string }[]>([]);
  const [results, setResults] = useState<{ passed: boolean; line: string }[]>([]);

  useEffect(() => { if (online) engine.packs().then((r) => setPacks(r.packs)).catch(() => setPacks(null)); }, [online]);

  async function openPack(id: string) {
    const r = await engine.packYaml(id);
    setCurrent(id); setYamlText(r.yaml); setDirty(false); setMessages([]); setResults([]);
  }
  const report = (kind: "ok" | "bad", text: string) => setMessages((m) => [...m, { kind, text }]);

  async function doValidate(): Promise<boolean> {
    setBusy("validating"); setMessages([]);
    try { const r = await engine.validate(yamlText); if (r.ok) report("ok", "Pack valid hai — koi problem nahi mili."); else r.problems.forEach((p) => report("bad", p)); return r.ok; }
    catch (e) { report("bad", String((e as Error).message)); return false; }
    finally { setBusy(null); }
  }
  async function doSave() {
    if (!(await doValidate())) return;
    setBusy("saving");
    try { const r = await engine.save(current, yamlText); report("ok", `Saved. Pichhla version ${r.backup} mein rakha hai.`); setDirty(false); setPacks((await engine.packs()).packs); }
    catch (e) { report("bad", String((e as Error).message)); }
    finally { setBusy(null); }
  }
  async function doSelftest() {
    setBusy("running scenarios"); setResults([]);
    try { const r = await engine.selftest(current); setResults(r.results); report(r.ok ? "ok" : "bad", r.summary || (r.ok ? "Saare scenarios paas." : "Upar failures dekho.")); }
    catch (e) { report("bad", String((e as Error).message)); }
    finally { setBusy(null); }
  }

  if (!online || packs === null) {
    return (
      <Page title="Pack Studio" sub="Ek business type = ek file. Yahin edit, validate aur test hota hai.">
        <Empty><p>Pack Studio live engine ke bina kaam nahi karta — ye files ko sach mein badalta hai.</p></Empty>
      </Page>
    );
  }

  return (
    <Page title="Pack Studio" sub="Edit karo, validate karo, uske apne scenarios chalao — phir ship karo.">
      <Panel title="Installed packs" hint="kholne ke liye click karo">
        <Register head={<><th>Pack</th><th>Language</th><th className="right">Services</th><th className="right">Scenarios</th><th>Health</th></>}>
          {packs.map((p) => (
            <tr key={p.pack_id} className="click" tabIndex={0} onClick={() => openPack(p.pack_id)} onKeyDown={(e) => { if (e.key === "Enter") openPack(p.pack_id); }}
                style={p.pack_id === current ? { background: "rgba(245,185,30,.14)" } : undefined}>
              <td><strong>{p.display_name}</strong> <span className="muted mono" style={{ fontSize: 12 }}>v{p.version}</span></td>
              <td>{p.language}</td>
              <td className="num right">{p.services}</td>
              <td className="num right">{p.scenarios}</td>
              <td>{p.issues.length === 0 ? <Chip kind="ok">valid</Chip> : <Chip kind="bad">{p.issues.length} issues</Chip>}</td>
            </tr>
          ))}
        </Register>
      </Panel>

      {current && (
        <Panel title={`${current}.yaml`} hint={dirty ? "unsaved changes" : "disk ke saath sync"}>
          <div className="body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <textarea className="input" value={yamlText} onChange={(e) => { setYamlText(e.target.value); setDirty(true); }} spellCheck={false} style={{ height: 440 }} aria-label="Pack YAML" />
            <div className="row">
              <button className="btn btn-ghost" onClick={doValidate} disabled={busy !== null}>Validate</button>
              <button className="btn btn-primary" onClick={doSave} disabled={busy !== null}>Validate &amp; save</button>
              <button className="btn btn-ghost" onClick={doSelftest} disabled={busy !== null}><Icon name="bolt" small />Is pack ke scenarios chalao</button>
              <a className="btn btn-ghost" href="/engine/talk" target="_blank" rel="noopener noreferrer">Try it live <Icon name="external" small /></a>
              {busy && <span className="muted">{busy}…</span>}
            </div>
            {messages.length > 0 && <div className="row">{messages.map((m, i) => <Chip key={i} kind={m.kind === "ok" ? "ok" : "bad"}><Icon name={m.kind === "ok" ? "check" : "x"} small />{m.text}</Chip>)}</div>}
            {results.length > 0 && (
              <Register head={<><th>Scenario run</th><th>Result</th></>}>
                {results.map((r, i) => (
                  <tr key={i}><td className="mono" style={{ fontSize: 12.5 }}>{r.line}</td><td>{r.passed ? <Chip kind="ok">pass</Chip> : <Chip kind="bad">fail</Chip>}</td></tr>
                ))}
              </Register>
            )}
          </div>
        </Panel>
      )}
    </Page>
  );
}
```

- [ ] **Step 8: Delete the old modules and build**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji/console"
rm src/api.ts src/live.ts src/mock.ts src/styles.css
grep -rn "localhost" src/ ; echo "(must print nothing)"
npm run build 2>&1 | tail -4
```
Expected: `✓ built in …`. If `tsc` reports an error, the message names the file and line — fix the type and rebuild.

- [ ] **Step 9: Commit**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G checkout -- console/tsconfig.tsbuildinfo 2>/dev/null
$G add -A console/src
$G commit -q -F - <<'MSG'
feat(console): the seven pages, engine-first, on the register surface

Aaj reads the engine's insights and refreshes every five seconds; Calls and
Call are the engine's own rows with painted repairs, tool chips and stamps;
Pramaan loads the export and verifies it in the browser with the engine's
verifier, with the same tamper button the public page has; Bhasha shows the
real lexicon and lets you probe a heard phrase; Packs and Studio read and
write the packs on disk. Every page falls back to labelled sample data when
the engine cannot be reached. The core-api token path and the fixtures it
served are gone.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 5: Visual pass for the console

**Files:**
- Modify: `engine/tests/visual_check.py`

- [ ] **Step 1: Add the console mode**

Replace the `PAGES`/`SIZES` block and the loop's page list so the script also covers the console when `CONSOLE_BASE` is set. The full file becomes:

```python
"""Screenshots and an axe-core run over the demo pages, and the console when asked.

    python -m haanji.cli serve --port 8090 &
    python tests/visual_check.py                                   # demo pages
    CONSOLE_BASE=http://127.0.0.1:5173 python tests/visual_check.py  # + console

Not a pytest test: it needs a browser and a network for fonts.
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("HAANJI_BASE", "http://127.0.0.1:8090")
CONSOLE = os.environ.get("CONSOLE_BASE")
OUT = os.environ.get("SHOTS", os.path.join(os.path.dirname(__file__), "..", "..", ".superpowers", "shots"))
AXE = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
PAGES = [(BASE, "", "landing"), (BASE, "talk", "talk"), (BASE, "whatsapp", "whatsapp"), (BASE, "verify", "verify")]
if CONSOLE:
    PAGES += [(CONSOLE, p, "console-" + p) for p in ("dashboard", "calls", "ledger", "lexicon", "packs", "studio")]
SIZES = {"desktop": (1440, 900), "mobile": (390, 844)}

os.makedirs(OUT, exist_ok=True)
problems = []


def settle(page, base, path):
    page.goto(f"{base}/{path}", wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    if base == BASE and path == "":
        try:
            page.wait_for_selector("#hero-call .stamp", timeout=25_000)
        except Exception:
            problems.append("landing: the hero never reached the stamp")
        page.evaluate("""async () => {
            const h = document.documentElement.scrollHeight;
            for (let y = 0; y < h; y += window.innerHeight * 0.6) {
                window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120));
            }
            window.scrollTo(0, 0); await new Promise(r => setTimeout(r, 400));
        }""")
    else:
        time.sleep(1.2)


def check(page, name, full):
    if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
        problems.append(f"{name}: horizontal overflow")
    page.add_script_tag(url=AXE)
    page.wait_for_function("window.axe !== undefined")
    result = page.evaluate("axe.run(document, {runOnly: ['wcag2a', 'wcag2aa']})")
    for v in result["violations"]:
        if v["impact"] in ("serious", "critical"):
            targets = ", ".join(n["target"][0] for n in v["nodes"][:3])
            problems.append(f"{name}: [{v['impact']}] {v['id']} — {v['help']} ({targets})")
    page.screenshot(path=os.path.join(OUT, name + ".png"), full_page=full)
    print("shot", name)


with sync_playwright() as p:
    browser = p.chromium.launch()
    for label, (w, h) in SIZES.items():
        ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
        page = ctx.new_page()
        for base, path, stem in PAGES:
            name = f"{stem}-{label}"
            settle(page, base, path)
            check(page, name, full=(stem == "landing"))
            if stem == "console-calls" and page.locator(".register tbody tr.click").count():
                page.locator(".register tbody tr.click").first.click()
                page.wait_for_selector(".transcript", timeout=10_000)
                time.sleep(0.8)
                check(page, f"console-call-{label}", full=False)
        ctx.close()
    browser.close()

print()
if problems:
    print("PROBLEMS")
    for line in problems:
        print(" -", line)
    sys.exit(1)
print("all pages: no overflow, no serious/critical axe issues; screenshots in", OUT)
```

- [ ] **Step 2: Run it against both servers**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
# engine on :8090 and console dev on :5173 must be running (see Global Constraints)
cd engine && CONSOLE_BASE=http://127.0.0.1:5173 $PY tests/visual_check.py 2>&1 | tail -16
```
Expected: 22 `shot` lines (10 pages × 2 sizes + call detail × 2) and the all-clear line. Fix anything it names (contrast → a darker ink token; overflow → `min-width: 0` or a scrolling wrapper; missing label → `aria-label`) and re-run.

- [ ] **Step 3: Look at the screenshots** — `console-dashboard-desktop`, `console-calls-desktop`, `console-call-desktop`, `console-ledger-desktop`, `console-lexicon-desktop`, `console-dashboard-mobile`, `console-call-mobile`. Judge: the top bar reads as the board; the register's red margin and ruled rows are visible; tiles count up; stamps and repairs look as they do on the demo pages; nothing clips at 390 px. Fix and re-run until it reads right.

- [ ] **Step 4: Commit**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G add engine/tests/visual_check.py console/src
$G commit -q -F - <<'MSG'
test(console): the visual and accessibility pass covers the console

With CONSOLE_BASE set, the Playwright + axe script screenshots the six
console routes and a call detail at desktop and phone widths alongside the
demo pages, with the same overflow and WCAG 2 A/AA checks.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 6: Ship

- [ ] **Step 1: Full verification**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
(cd engine && $PY -m pytest -q | tail -1)            # 183 passed
(cd console && npx vitest run 2>&1 | tail -2 && npm run build 2>&1 | tail -2)
```

- [ ] **Step 2: Merge and push; deploy the console**

```bash
G=/Library/Developer/CommandLineTools/usr/bin/git
$G checkout -q main && $G merge -q --ff-only console-signboard && $G branch -d console-signboard
$G -c credential.helper='!gh auth git-credential' push
(cd console && vercel deploy --prod --yes 2>&1 | grep -E 'Aliased|Error')
```
Render rebuilds the engine (the lexicon endpoint) on its own.

- [ ] **Step 3: Verify live**

```bash
until curl -fsS -o /dev/null --max-time 60 "https://haanji-engine.onrender.com/api/lexicon?pack=dental_clinic"; do sleep 20; done
curl -s "https://haanji-engine.onrender.com/api/lexicon?pack=dental_clinic&probe=rut%20kanal" | grep -o '"probe":{[^}]*}'
curl -s https://haanji-kappa.vercel.app/ | grep -o 'HaanJi Console'
curl -s -o /dev/null -w 'console /engine/api/insights -> %{http_code}\n' "https://haanji-kappa.vercel.app/engine/api/insights?pack=dental_clinic"
gh run list -R aritra-25hazra/haanji --limit 1
```
Then open https://haanji-kappa.vercel.app in a browser: the chip reads LIVE, Aaj shows the engine's numbers, Calls lists the calls made on the live /talk, Pramaan shows a VALID stamp, Bhasha's probe answers `rut kanal`.
