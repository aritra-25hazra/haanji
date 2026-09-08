import type {
  ConversationDetail, ConversationSummary, Dashboard, LexiconEntry, Verification,
} from "./types";

/**
 * Fixtures taken from a real run of the engine's demo scenario, so the console
 * shows the same conversation the benchmark measured rather than invented
 * numbers.
 */
export const dashboard = (): Dashboard => ({
  calls_today: 63,
  bookings_today: 28,
  leads_open: 7,
  answer_rate: 1.0,
  booking_rate: 0.444,
  outcomes: { BOOKED: 28, FAQ_ANSWERED: 19, LEAD_CAPTURED: 7, HANDED_OFF: 6, ABANDONED: 3 },
  latency: { p50: 137, p90: 242, p95: 268 },
  corrections_today: 41,
  speculation_hit_rate: 0.455,
  by_hour: [
    { hour: "09", calls: 4, booked: 2 }, { hour: "10", calls: 9, booked: 5 },
    { hour: "11", calls: 11, booked: 6 }, { hour: "12", calls: 8, booked: 3 },
    { hour: "13", calls: 3, booked: 1 }, { hour: "14", calls: 2, booked: 0 },
    { hour: "15", calls: 6, booked: 2 }, { hour: "16", calls: 7, booked: 3 },
    { hour: "17", calls: 5, booked: 3 }, { hour: "18", calls: 5, booked: 2 },
    { hour: "19", calls: 3, booked: 1 },
  ],
});

const BASE_ID = "6f1c9b2a-0d44-4a11-9c8e-2b5f3a71c001";

export const conversations = (): ConversationSummary[] => [
  { conversation_id: BASE_ID, channel: "PHONE", caller_phone: "98XXXXXX10",
    started_at: "2026-09-07T11:04:12+05:30", outcome: "BOOKED", duration_ms: 41_300 },
  { conversation_id: BASE_ID.replace("001", "002"), channel: "WHATSAPP",
    caller_phone: "98XXXXXX78", started_at: "2026-09-07T10:51:02+05:30",
    outcome: "FAQ_ANSWERED", duration_ms: 22_700 },
  { conversation_id: BASE_ID.replace("001", "003"), channel: "PHONE",
    caller_phone: "99XXXXXX33", started_at: "2026-09-07T10:33:47+05:30",
    outcome: "LEAD_CAPTURED", duration_ms: 28_100 },
  { conversation_id: BASE_ID.replace("001", "004"), channel: "PHONE",
    caller_phone: "97XXXXXX00", started_at: "2026-09-07T10:12:19+05:30",
    outcome: "HANDED_OFF", duration_ms: 9_400 },
  { conversation_id: BASE_ID.replace("001", "005"), channel: "WEB",
    caller_phone: "—", started_at: "2026-09-07T09:58:03+05:30",
    outcome: "BOOKED", duration_ms: 37_800 },
];

export const conversation = (id: string): ConversationDetail => ({
  ...conversations()[0]!,
  conversation_id: id,
  ended_at: "2026-09-07T11:04:53+05:30",
  turns: [
    { seq: 1, speaker: "agent", text: "Haanji, Smile Care Dental. Main aapki kya madad karun?",
      raw_text: null, corrections: [], tool_calls: [], latency_ms: null, interrupted: false },
    { seq: 2, speaker: "caller", text: "haan ji mujhe root canal karwana tha",
      raw_text: "haan ji mujhe rut kanal karwana tha",
      corrections: [{ from_token: "rut kanal", to_surface: "root canal",
                      asr_confidence: 0.32, ngram: 2 }],
      tool_calls: [], latency_ms: 22, interrupted: false },
    { seq: 3, speaker: "agent", text: "Theek hai. Kis din ka time dekhun?", raw_text: null,
      corrections: [], tool_calls: [], latency_ms: null, interrupted: false },
    { seq: 4, speaker: "caller", text: "kal subah ka time mil jayega", raw_text: null,
      corrections: [], tool_calls: ["check_availability"],
      speculation_hits: ["check_availability"], latency_ms: 31, interrupted: false },
    { seq: 5, speaker: "agent",
      text: "Kal subah saade 9 baje khaali hai, Dr Sheikh ke saath. Ya phir subah saade 10 baje. Chalega?",
      raw_text: null, corrections: [], tool_calls: [], latency_ms: null, interrupted: false },
    { seq: 6, speaker: "caller", text: "haan ji wahi theek hai", raw_text: null,
      corrections: [], tool_calls: [], latency_ms: 10, interrupted: true },
    { seq: 7, speaker: "agent", text: "Bas aapka naam aur mobile number bata dijiye.",
      raw_text: null, corrections: [], tool_calls: [], latency_ms: null, interrupted: false },
    { seq: 8, speaker: "caller", text: "mera naam Vijay Sharma hai number 98XXXXXX10",
      raw_text: null, corrections: [], tool_calls: [], latency_ms: 9, interrupted: false },
    { seq: 9, speaker: "agent",
      text: "Ek baar dohra deta hoon — root canal, kal subah saade 9 baje Dr Sheikh ke saath, Vijay Sharma naam se. Confirm kar dun?",
      raw_text: null, corrections: [], tool_calls: [], latency_ms: null, interrupted: false },
    { seq: 10, speaker: "caller", text: "haan confirm kar do", raw_text: null, corrections: [],
      tool_calls: ["book_appointment"], latency_ms: 301, interrupted: false },
    { seq: 11, speaker: "agent",
      text: "Ho gaya. Kal subah saade 9 baje, Dr Sheikh ke saath. Confirmation code 2504-7863.",
      raw_text: null, corrections: [], tool_calls: [], latency_ms: null, interrupted: false },
  ],
  receipts: [{
    seq: 1, short_code: "2504-7863", action: "book_appointment",
    action_args: { service: "root canal", starts_at: "2026-09-08T09:30:00+05:30",
                   staff: "Dr Sheikh", phone: "98XXXXXX10" },
    confirmation: {
      prompt_text: "Ek baar dohra deta hoon — root canal, kal subah saade 9 baje Dr Sheikh ke saath, Vijay Sharma naam se. Confirm kar dun?",
      reply_text: "haan confirm kar do", asr_confidence: 0.911, audio_offset_ms: 890,
    },
    transcript_excerpt: "agent: … Confirm kar dun? | caller: haan confirm kar do",
    occurred_at: "2026-09-07T11:04:51+05:30",
    chain_hash: "25047863e7df1151dc2c2f0bdc583cc995b6b2e4dc2b704d3f0a1e6c8b2d9f47",
  }],
});

export const verification = (): Verification => ({
  ok: true, checked: 1284, first_broken_seq: null, reason: null,
  public_key: "9f3a1c77d0b4e2685aa1c9f0d3b7e4128c65af90d2e1b7433c8f0a95e6d2417b",
});

export const lexicon = (): LexiconEntry[] => [
  { surface: "root canal", entry_type: "SERVICE", variants: ["rct", "root canal treatment"],
    phonetic_key: "RTKNR", weight: 1.35, repairs_30d: 61 },
  { surface: "teeth cleaning", entry_type: "SERVICE", variants: ["cleaning", "scaling", "safai"],
    phonetic_key: "TTKRNNG", weight: 1.25, repairs_30d: 44 },
  { surface: "full body checkup", entry_type: "SERVICE", variants: ["checkup"],
    phonetic_key: "fRPTCKP", weight: 1.25, repairs_30d: 29 },
  { surface: "Dr Sheikh", entry_type: "STAFF", variants: ["Doctor Shaik"],
    phonetic_key: "TRSK", weight: 1.18, repairs_30d: 33 },
  { surface: "Vijay Nagar", entry_type: "PLACE", variants: [],
    phonetic_key: "VJNGR", weight: 1.00, repairs_30d: 18 },
  { surface: "dental implant", entry_type: "SERVICE", variants: ["implant", "implants"],
    phonetic_key: "TNTRPNT", weight: 1.25, repairs_30d: 12 },
];

export const packs = (): string[] =>
  ["dental_clinic", "salon_spa", "diagnostic_lab", "coaching_institute"];
