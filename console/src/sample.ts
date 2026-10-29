/**
 * What the public demo shows when the engine cannot be reached and nobody is
 * signed in: the README's demo call and the benchmark's numbers, in the
 * engine's own shapes. Every page labels it as sample data, and the console
 * never substitutes it for a signed-in owner (see state.tsx `mode`).
 */
import { dayOfWeek, eachDay } from "./dates";
import type { Booking, CallRow, Customer, Export, Insights, Lexicon, PackSummary, Payment, Status, Turn, WaitlistEntry } from "./types";

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
  { call_id: "sample-006", channel: "PHONE", phone: "97XXXXXX41", started_at: "2026-09-07T10:20:31",
    ended_at: "2026-09-07T10:21:02", outcome: "REFUSED", corrections: 0, spec_started: 0, spec_hits: 0,
    latency_p50: 0.7,
    turns_json: JSON.stringify([{ heard: "daant mein dard hai koi dawai bata do", corrected: "daant mein dard hai koi dawai bata do",
      said: "Dawai main nahi bata sakti — doctor dekh ke batayenge. Aaj shaam ka time dekhun?", tools: [], speculation_hits: [],
      guard: "no_medical_advice", latency_ms: 0.7, interrupted: false, corrections: [] }]),
    receipts_json: "[]" },
  { call_id: "sample-004", channel: "PHONE", phone: null, started_at: "2026-09-07T10:12:09",
    ended_at: null, outcome: "HANDED_OFF", corrections: 0, spec_started: 0, spec_hits: 0,
    latency_p50: 0.5, turns_json: "[]", receipts_json: "[]" },
  { call_id: "sample-005", channel: "WEB", phone: "98XXXXXX02", started_at: "2026-09-07T09:58:40",
    ended_at: null, outcome: "BOOKED", corrections: 1, spec_started: 2, spec_hits: 1,
    latency_p50: 137, turns_json: "[]", receipts_json: JSON.stringify(["1F3A-90C2"]) },
];

/** A week of demo bookings laid over whatever dates are on screen, so the
 *  calendar always has something to show. Deterministic per weekday. */
const DAY_PLAN: Record<number, Omit<Booking, "booking_id" | "date" | "created_at" | "receipt_code">[]> = {
  1: [
    { service: "root canal", staff: "Dr Sheikh", time: "09:30", duration_min: 60, customer_name: "Vijay Sharma", phone: "9876543210", status: "CONFIRMED", paid: false, deposit_inr: 500, payment_link: "/pay/sample-1", reminder_sent_at: null },
    { service: "cleaning", staff: "Dr Mehta", time: "11:00", duration_min: 30, customer_name: "Pooja Verma", phone: "9898989878", status: "CONFIRMED", paid: true, deposit_inr: 300, payment_link: null, reminder_sent_at: "2026-10-27T18:00:00" },
  ],
  2: [
    { service: "braces consult", staff: "Dr Mehta", time: "16:00", duration_min: 30, customer_name: "Arjun Nair", phone: "9812345602", status: "CONFIRMED", paid: false, deposit_inr: 0, payment_link: null, reminder_sent_at: null },
  ],
  3: [
    { service: "cleaning", staff: "Dr Sheikh", time: "10:30", duration_min: 30, customer_name: "Rekha Jain", phone: "9933221133", status: "NO_SHOW", paid: false, deposit_inr: 0, payment_link: null, reminder_sent_at: "2026-10-28T18:00:00" },
    { service: "root canal", staff: "Dr Sheikh", time: "12:00", duration_min: 60, customer_name: "Imran Khan", phone: "9700011141", status: "CONFIRMED", paid: true, deposit_inr: 500, payment_link: null, reminder_sent_at: null },
    { service: "filling", staff: "Dr Mehta", time: "17:30", duration_min: 30, customer_name: "Sana Sheikh", phone: "9811112222", status: "CANCELLED", paid: false, deposit_inr: 0, payment_link: null, reminder_sent_at: null },
  ],
  4: [
    { service: "filling", staff: "Dr Mehta", time: "11:30", duration_min: 30, customer_name: "Meera Iyer", phone: "9822334455", status: "COMPLETED", paid: true, deposit_inr: 300, payment_link: null, reminder_sent_at: "2026-10-28T18:00:00" },
  ],
  5: [
    { service: "cleaning", staff: "Dr Sheikh", time: "09:00", duration_min: 30, customer_name: "Vijay Sharma", phone: "9876543210", status: "CONFIRMED", paid: false, deposit_inr: 0, payment_link: null, reminder_sent_at: null },
    { service: "braces consult", staff: "Dr Mehta", time: "15:00", duration_min: 30, customer_name: "Kabir Das", phone: "9845612378", status: "CONFIRMED", paid: false, deposit_inr: 500, payment_link: "/pay/sample-2", reminder_sent_at: null },
  ],
  6: [
    { service: "root canal", staff: "Dr Sheikh", time: "10:00", duration_min: 60, customer_name: "Pooja Verma", phone: "9898989878", status: "CONFIRMED", paid: false, deposit_inr: 0, payment_link: null, reminder_sent_at: null },
  ],
};

export const sample = {
  status: SAMPLE_STATUS,

  insights(): Insights {
    return {
      tenant_id: "dental_clinic", generated_at: "2026-09-07T19:00:00",
      calls_total: 63, calls_today: 63,
      outcomes: { BOOKED: 28, FAQ_ANSWERED: 19, LEAD_CAPTURED: 7, HANDED_OFF: 4, REFUSED: 2, ABANDONED: 3 },
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
        "2 callers asked for medicine advice; the agent declined and offered a slot instead.",
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

  bookings(from: string, to: string): Booking[] {
    const out: Booking[] = [];
    for (const date of eachDay(from, to)) {
      const dow = dayOfWeek(date);
      (DAY_PLAN[dow] ?? []).forEach((b, i) => {
        const n = (Number(date.replace(/-/g, "")) * 7 + i * 131) % 9000 + 1000;
        out.push({ ...b, booking_id: `sample-${date}-${i}`, date, created_at: `${date}T08:00:00`, receipt_code: `${n}-${(n * 3) % 9000 + 1000}` });
      });
    }
    return out;
  },

  customers(query = ""): Customer[] {
    const all: Customer[] = [
      { phone: "9876543210", name: "Vijay Sharma", last_service: "root canal", last_visit: "2026-10-27", visits: 4, bookings: 5, no_shows: 0 },
      { phone: "9898989878", name: "Pooja Verma", last_service: "cleaning", last_visit: "2026-10-20", visits: 6, bookings: 6, no_shows: 0 },
      { phone: "9933221133", name: "Rekha Jain", last_service: "cleaning", last_visit: "2026-08-02", visits: 1, bookings: 3, no_shows: 2 },
      { phone: "9812345602", name: "Arjun Nair", last_service: "braces consult", last_visit: null, visits: 0, bookings: 1, no_shows: 0 },
      { phone: "9700011141", name: "Imran Khan", last_service: "root canal", last_visit: "2026-09-14", visits: 2, bookings: 2, no_shows: 0 },
      { phone: "9822334455", name: "Meera Iyer", last_service: "filling", last_visit: "2026-10-29", visits: 3, bookings: 3, no_shows: 0 },
    ];
    const needle = query.trim().toLowerCase();
    return needle ? all.filter((c) => c.name.toLowerCase().includes(needle) || c.phone.endsWith(needle)) : all;
  },

  waitlist(): WaitlistEntry[] {
    return [
      { entry_id: "wl-sample-1", phone: "9811112222", name: "Sana Sheikh", service: "filling", date: "2026-10-30", period: "evening", created_at: "2026-10-28T19:12:00", offered_at: null, status: "WAITING" },
      { entry_id: "wl-sample-2", phone: "9845612378", name: "Kabir Das", service: "braces consult", date: "2026-10-31", period: "morning", created_at: "2026-10-28T20:40:00", offered_at: "2026-10-29T09:02:00", status: "OFFERED" },
    ];
  },

  payments(): Payment[] {
    return [
      { payment_id: "pay-sample-1", booking_id: "sample-1", amount_inr: 500, status: "CREATED", link: "/pay/sample-1", created_at: "2026-10-29T10:05:00", paid_at: null },
      { payment_id: "pay-sample-2", booking_id: "sample-2", amount_inr: 500, status: "PAID", link: "/pay/sample-2", created_at: "2026-10-28T16:40:00", paid_at: "2026-10-28T16:43:12" },
      { payment_id: "pay-sample-3", booking_id: "sample-3", amount_inr: 300, status: "EXPIRED", link: "/pay/sample-3", created_at: "2026-10-26T11:00:00", paid_at: null },
    ];
  },
};
