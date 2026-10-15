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
