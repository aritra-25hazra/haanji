export type Outcome =
  | "BOOKED" | "FAQ_ANSWERED" | "LEAD_CAPTURED" | "HANDED_OFF" | "ABANDONED" | "IN_PROGRESS";

export type Channel = "PHONE" | "WHATSAPP" | "WEB";

export interface Correction {
  from_token: string;
  to_surface: string;
  asr_confidence: number;
  ngram: number;
}

export interface Turn {
  seq: number;
  speaker: "caller" | "agent";
  text: string;
  raw_text: string | null;
  corrections: Correction[];
  tool_calls: string[];
  speculation_hits?: string[];
  latency_ms: number | null;
  interrupted: boolean;
}

export interface Receipt {
  seq: number;
  short_code: string;
  action: string;
  action_args: Record<string, unknown>;
  confirmation: {
    prompt_text?: string;
    reply_text?: string;
    asr_confidence?: number;
    audio_offset_ms?: number;
  };
  transcript_excerpt: string;
  occurred_at: string;
  chain_hash: string;
}

export interface ConversationSummary {
  conversation_id: string;
  channel: Channel;
  caller_phone: string;
  started_at: string;
  outcome: Outcome;
  duration_ms: number;
}

export interface ConversationDetail extends ConversationSummary {
  ended_at: string | null;
  turns: Turn[];
  receipts: Receipt[];
}

export interface Dashboard {
  calls_today: number;
  bookings_today: number;
  leads_open: number;
  answer_rate: number;
  booking_rate: number;
  outcomes: Record<string, number>;
  latency: { p50: number; p90: number; p95: number };
  corrections_today: number;
  speculation_hit_rate: number;
  by_hour: { hour: string; calls: number; booked: number }[];
}

export interface Verification {
  ok: boolean;
  checked: number;
  first_broken_seq: number | null;
  reason: string | null;
  public_key: string;
}

export interface LexiconEntry {
  surface: string;
  entry_type: "SERVICE" | "STAFF" | "PLACE" | "BRAND" | "PHRASE";
  variants: string[];
  phonetic_key: string;
  weight: number;
  repairs_30d: number;
}
