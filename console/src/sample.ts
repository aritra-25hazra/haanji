/**
 * What the public demo shows when the engine cannot be reached and nobody is
 * signed in: the README's demo call and the benchmark's numbers, in the
 * engine's own shapes. Every page labels it as sample data, and the console
 * never substitutes it for a signed-in owner (see state.tsx `mode`).
 */
import { addDays, dayOfWeek, eachDay, today } from "./dates";
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

const HAND_CALLS: CallRow[] = [
  { call_id: "sample-001", channel: "PHONE", phone: "98XXXXXX10", started_at: `${today()}T11:04:12`,
    ended_at: `${today()}T11:04:53`, outcome: "BOOKED", corrections: 1, spec_started: 1, spec_hits: 1,
    latency_p50: 31, turns_json: JSON.stringify(DEMO_TURNS), receipts_json: JSON.stringify(["2504-7863"]) },
  { call_id: "sample-002", channel: "WHATSAPP", phone: "98XXXXXX78", started_at: `${today()}T10:51:02`,
    ended_at: null, outcome: "FAQ_ANSWERED", corrections: 0, spec_started: 0, spec_hits: 0,
    latency_p50: 0.6, turns_json: "[]", receipts_json: "[]" },
  { call_id: "sample-003", channel: "PHONE", phone: "99XXXXXX33", started_at: `${today()}T10:33:47`,
    ended_at: null, outcome: "LEAD_CAPTURED", corrections: 2, spec_started: 1, spec_hits: 0,
    latency_p50: 180, turns_json: "[]", receipts_json: "[]" },
  { call_id: "sample-006", channel: "PHONE", phone: "97XXXXXX41", started_at: `${today()}T10:20:31`,
    ended_at: `${today()}T10:21:02`, outcome: "REFUSED", corrections: 0, spec_started: 0, spec_hits: 0,
    latency_p50: 0.7,
    turns_json: JSON.stringify([{ heard: "daant mein dard hai koi dawai bata do", corrected: "daant mein dard hai koi dawai bata do",
      said: "Dawai main nahi bata sakti — doctor dekh ke batayenge. Aaj shaam ka time dekhun?", tools: [], speculation_hits: [],
      guard: "no_medical_advice", latency_ms: 0.7, interrupted: false, corrections: [] }]),
    receipts_json: "[]" },
  { call_id: "sample-004", channel: "PHONE", phone: null, started_at: `${today()}T10:12:09`,
    ended_at: null, outcome: "HANDED_OFF", corrections: 0, spec_started: 0, spec_hits: 0,
    latency_p50: 0.5, turns_json: "[]", receipts_json: "[]" },
  { call_id: "sample-005", channel: "WEB", phone: "98XXXXXX02", started_at: `${today()}T09:58:40`,
    ended_at: null, outcome: "BOOKED", corrections: 1, spec_started: 2, spec_hits: 1,
    latency_p50: 137, turns_json: "[]", receipts_json: JSON.stringify(["1F3A-90C2"]) },
];


// ── a full sample shop: 100 customers and the day they make ────────────────
// Made up, deterministic (the same every time the page opens on a given
// day), shaped like the dental pack: its services, prices and doctors. Every
// page that shows it says SAMPLE; none of it ever reaches the engine.

function rng(seed: number): () => number {
  let a = seed | 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const pick = <T,>(r: () => number, xs: readonly T[]): T => xs[Math.floor(r() * xs.length)]!;
function weighted<T>(r: () => number, xs: readonly (readonly [T, number])[]): T {
  const total = xs.reduce((a, [, w]) => a + w, 0);
  let x = r() * total;
  for (const [v, w] of xs) { if ((x -= w) < 0) return v; }
  return xs[xs.length - 1]![0];
}
const hhmm = (min: number) => `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;

const FIRST = ["Aarav", "Aditi", "Akash", "Ananya", "Anil", "Anjali", "Arjun", "Ayesha", "Deepak", "Divya", "Farhan", "Gaurav",
  "Harsh", "Isha", "Kabir", "Kavya", "Kiran", "Lakshmi", "Manish", "Meera", "Mohit", "Naina", "Neha", "Nikhil", "Pooja",
  "Pradeep", "Priya", "Rahul", "Rajesh", "Ritu", "Rohan", "Sakshi", "Sana", "Sanjay", "Shreya", "Simran", "Sneha", "Suresh",
  "Tanvi", "Tarun", "Uma", "Varun", "Vikram", "Yash", "Zoya", "Imran", "Gurpreet", "Fatima", "Joseph", "Lalit"] as const;
const LAST = ["Sharma", "Verma", "Gupta", "Iyer", "Nair", "Khan", "Singh", "Jain", "Mehta", "Patel", "Reddy", "Das",
  "Bose", "Kulkarni", "Joshi", "Malhotra", "Chopra", "Pillai", "Sheikh", "Agarwal", "Rao", "Mishra", "Kapoor", "Desai"] as const;
const SERVICES = [
  { name: "teeth cleaning", price: 1200, min: 30, staff: ["Dr Sheikh", "Dr Malhotra", "Dr Iyer"], w: 30, ask: "mujhe teeth cleaning karwani hai" },
  { name: "full body checkup", price: 800, min: 30, staff: ["Dr Malhotra"], w: 22, ask: "daant ka checkup karwana hai" },
  { name: "root canal", price: 6500, min: 60, staff: ["Dr Sheikh", "Dr Iyer"], w: 16, ask: "haan ji mujhe root canal karwana tha" },
  { name: "braces consultation", price: 1000, min: 45, staff: ["Dr Iyer"], w: 13, ask: "braces ke baare mein doctor se milna hai" },
  { name: "tooth extraction", price: 2500, min: 45, staff: ["Dr Sheikh", "Dr Malhotra"], w: 11, ask: "akal daad nikalwani hai" },
  { name: "dental implant", price: 28000, min: 90, staff: ["Dr Sheikh"], w: 4, ask: "implant ke liye appointment chahiye" },
] as const;
const LEAD_ASKS = ["Sunday ko slot milega kya", "shaam 8 baje ke baad ka time hai kya", "doctor se seedha baat karni hai",
  "insurance claim ke baare mein poochna tha", "bachche ke daant mein dard hai, aaj hi dikhana hai"];

export const SAMPLE_CUSTOMERS: Customer[] = (() => {
  const r = rng(7);
  const out: Customer[] = [];
  const used = new Set<string>();
  while (out.length < 100) {
    const name = `${pick(r, FIRST)} ${pick(r, LAST)}`;
    if (used.has(name)) continue;
    used.add(name);
    const visits = weighted(r, [[0, 12], [1, 30], [2, 22], [3, 14], [4, 9], [6, 6], [9, 3]] as const);
    const noShows = weighted(r, [[0, 82], [1, 13], [2, 5]] as const);
    const svc = weighted(r, SERVICES.map((x) => [x, x.w] as const));
    const phone = `9${1 + Math.floor(r() * 8)}XXXXX${String(100 + out.length * 7).slice(-3)}`;
    out.push({ phone, name, last_service: visits ? svc.name : null, last_visit: visits ? addDays(today(), -Math.floor(r() * 150) - 1) : null,
               visits, bookings: visits + noShows + (r() < .25 ? 1 : 0), no_shows: noShows });
  }
  return out.sort((a, b) => (b.last_visit ?? "").localeCompare(a.last_visit ?? ""));
})();

function makeTurns(ask: string, said: string, tools: string[]): string {
  const t: Turn = { heard: ask, corrected: ask, said, tools, speculation_hits: [], guard: null, latency_ms: 140, interrupted: false, corrections: [] };
  return JSON.stringify([t]);
}

/** Today's calls: the six written by hand above, then a day's worth more. */
const CALLS: CallRow[] = (() => {
  const r = rng(Number(today().replace(/-/g, "")));
  const out: CallRow[] = [...HAND_CALLS];
  const hours = [[9, 6], [10, 11], [11, 14], [12, 10], [13, 5], [14, 4], [15, 8], [16, 10], [17, 12], [18, 9], [19, 6], [20, 3]] as const;
  for (let i = 0; i < 112; i++) {
    const h = weighted(r, hours);
    const at = `${today()}T${hhmm(h * 60 + Math.floor(r() * 60))}:${String(Math.floor(r() * 60)).padStart(2, "0")}`;
    const outcome = weighted(r, [["BOOKED", 45], ["FAQ_ANSWERED", 24], ["LEAD_CAPTURED", 13], ["HANDED_OFF", 5], ["REFUSED", 4], ["ABANDONED", 9]] as const);
    const svc = weighted(r, SERVICES.map((x) => [x, x.w] as const));
    const c = r() < .7 ? pick(r, SAMPLE_CUSTOMERS) : null;
    const ask = outcome === "LEAD_CAPTURED" || outcome === "HANDED_OFF" ? pick(r, LEAD_ASKS) : svc.ask;
    const spec = outcome === "BOOKED" ? 1 + Math.floor(r() * 2) : r() < .3 ? 1 : 0;
    out.push({
      call_id: `sample-g${String(i).padStart(3, "0")}`, channel: weighted(r, [["PHONE", 55], ["WHATSAPP", 40], ["WEB", 5]] as const),
      phone: c ? c.phone : `9${1 + Math.floor(r() * 8)}XXXXX${String(Math.floor(r() * 900) + 100)}`, started_at: at, ended_at: at,
      outcome, corrections: weighted(r, [[0, 70], [1, 22], [2, 8]] as const), spec_started: spec, spec_hits: spec ? Math.floor(r() * (spec + 1)) : 0,
      latency_p50: Math.round(110 + r() * 220), receipts_json: "[]",
      turns_json: makeTurns(ask, outcome === "BOOKED" ? `${svc.name} ke liye slot dekhta hoon.` : "Theek hai, number note kar liya.", outcome === "BOOKED" ? ["check_availability"] : []),
      // a booked call carries its service's price for the day's revenue below
      ...(outcome === "BOOKED" ? { _price: svc.price } : {}),
    } as CallRow);
  }
  return out.sort((a, b) => b.started_at.localeCompare(a.started_at));
})();

/** A working day's bookings for any date: 6 to 12, over the three doctors,
 *  never on Sunday (the clinic is closed), past days completed or no-show. */
function bookingsOn(date: string): Booking[] {
  if (dayOfWeek(date) === 0) return [];
  const r = rng(Number(date.replace(/-/g, "")) * 31);
  const n = 6 + Math.floor(r() * 7);
  const free: Record<string, number> = { "Dr Sheikh": 9 * 60 + 30, "Dr Malhotra": 9 * 60 + 30, "Dr Iyer": 9 * 60 + 30 };
  const past = date < today();
  const out: Booking[] = [];
  for (let i = 0; i < n; i++) {
    const svc = weighted(r, SERVICES.map((x) => [x, x.w] as const));
    const staff = pick(r, svc.staff);
    let start = free[staff]! + Math.floor(r() * 3) * 30;
    if (start < 15 * 60 + 30 && start + svc.min > 14 * 60) start = 15 * 60 + 30;   // the lunch break
    if (start + svc.min > 20 * 60) continue;
    free[staff] = start + svc.min;
    const c = pick(r, SAMPLE_CUSTOMERS);
    const status = past ? weighted(r, [["COMPLETED", 86], ["NO_SHOW", 9], ["CANCELLED", 5]] as const)
                        : weighted(r, [["CONFIRMED", 94], ["CANCELLED", 6]] as const);
    const code = (Number(date.replace(/-/g, "")) * 7 + i * 131) % 9000 + 1000;
    out.push({ booking_id: `sample-${date}-${i}`, service: svc.name, staff, date, time: hhmm(start), duration_min: svc.min,
               customer_name: c.name, phone: c.phone, status, receipt_code: `${code}-${(code * 3) % 9000 + 1000}`,
               created_at: `${addDays(date, -1)}T18:00:00`, paid: svc.price >= 2500 && r() < .6, deposit_inr: svc.price >= 2500 ? 500 : 0,
               payment_link: null, reminder_sent_at: null });
  }
  return out;
}

export const sample = {
  status: SAMPLE_STATUS,

  insights(): Insights {
    const outcomes: Record<string, number> = {};
    const byHour = new Map<string, { hour: string; calls: number; booked: number }>();
    let revenue = 0, corrections = 0, specStarted = 0, specHits = 0;
    for (const c of CALLS) {
      const o = c.outcome ?? "IN_PROGRESS";
      outcomes[o] = (outcomes[o] ?? 0) + 1;
      const h = c.started_at.slice(11, 13);
      const slot = byHour.get(h) ?? { hour: h, calls: 0, booked: 0 };
      slot.calls++; if (o === "BOOKED") slot.booked++;
      byHour.set(h, slot);
      revenue += (c as CallRow & { _price?: number })._price ?? (o === "BOOKED" ? 1200 : 0);
      corrections += c.corrections; specStarted += c.spec_started ?? 0; specHits += c.spec_hits;
    }
    const booked = outcomes.BOOKED ?? 0;
    const hours = [...byHour.values()].sort((a, b) => a.hour.localeCompare(b.hour));
    const busiest = hours.reduce((m, x) => (x.calls > m.calls ? x : m), hours[0]!);
    return {
      tenant_id: "dental_clinic", generated_at: `${today()}T19:00:00`,
      calls_total: CALLS.length, calls_today: CALLS.length, outcomes, by_hour: hours,
      bookings_confirmed: booked, revenue_booked_inr: revenue, leads_open: outcomes.LEAD_CAPTURED ?? 0,
      missed_calls: { total: 14, recovered: 10 }, corrections_total: corrections,
      speculation: { started: specStarted, hits: specHits, hit_rate: specStarted ? specHits / specStarted : 0 },
      cost: { ai_per_call_inr: 3.16, receptionist_per_call_inr: 9.23 },
      insights: [
        `${CALLS.length} calls aayi; ${booked} booking bani (${Math.round((booked * 100) / CALLS.length)}%).`,
        `Calendar par bookings catalogue ke daam se lagbhag ₹${revenue.toLocaleString("en-IN")} ki hain.`,
        "14 missed calls mein se 10 WhatsApp se wapas aaye.",
        `Sabse busy ghanta: ${busiest.hour}:00, ${busiest.calls} calls.`,
        `Bhasha Bridge ne ${corrections} galat sune shabd theek kiye.`,
        "Sample data: 100 nakli customers ka ek din. Asli numbers ke liye Sample switch band karo.",
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
    return eachDay(from, to).flatMap(bookingsOn);
  },

  customers(query = ""): Customer[] {
    const needle = query.trim().toLowerCase();
    return needle ? SAMPLE_CUSTOMERS.filter((c) => c.name.toLowerCase().includes(needle) || c.phone.endsWith(needle)) : SAMPLE_CUSTOMERS;
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
