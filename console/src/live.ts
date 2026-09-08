/**
 * Live mode against the Python demo server.
 *
 * The console was designed on fixtures; when `haanji serve` is running, these
 * helpers pull real rows through the /engine proxy instead. Every caller
 * handles the offline case, so the console never breaks when the server is
 * down — it says so and falls back to the sample dataset.
 */

export interface LiveInsights {
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

export interface LiveCallRow {
  call_id: string;
  channel: string;
  phone: string | null;
  started_at: string;
  outcome: string;
  corrections: number;
  spec_hits: number;
  latency_p50: number | null;
  turns_json: string;
  receipts_json: string;
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

const BASE = "/engine";

async function get<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`${BASE}${path}`, { signal: AbortSignal.timeout(2500) });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as T;
}

export const live = {
  status: () => get<{ version: string; packs: string[]; default_pack: string }>("/api/status"),
  insights: (pack: string) => get<LiveInsights>(`/api/insights?pack=${pack}`),
  calls: (pack: string) =>
    get<{ conversations: LiveCallRow[] }>(`/api/conversations?pack=${pack}`),
  call: (pack: string, id: string) => get<LiveCallRow>(`/api/conversations/${id}?pack=${pack}`),
  packs: () => get<{ packs: PackSummary[] }>("/api/packs"),
  packYaml: (id: string) => get<{ yaml: string }>(`/api/packs/${id}`),
  validate: (yaml: string) =>
    send<{ ok: boolean; problems: string[] }>("POST", "/api/packs/validate", { yaml }),
  save: (id: string, yaml: string) =>
    send<{ ok: boolean; problems: string[]; backup: string }>("PUT", `/api/packs/${id}`, { yaml }),
  selftest: (id: string) =>
    send<{ ok: boolean; results: { passed: boolean; line: string }[]; summary: string }>(
      "POST", `/api/packs/${id}/selftest`),
};
