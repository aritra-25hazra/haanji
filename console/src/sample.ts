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
