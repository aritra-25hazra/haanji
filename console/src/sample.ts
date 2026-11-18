import { t } from "./i18n";
/**
 * The made-up shop the console shows in sample mode: when the engine cannot
 * be reached and nobody is signed in, or when the Sample switch is on. Every
 * page labels it as sample data, and the console never substitutes it for a
 * signed-in owner (see state.tsx `mode`).
 *
 * One seeded generator per pack, and one order of making things: the
 * bookings first (from the pack's own services, prices, staff and hours, in
 * packs.json, written from packs/*.yaml by research/harness/console_packs.py),
 * then everything else from those bookings: the customers' visits and
 * no-shows, today's calls and their transcripts, one ledger receipt per
 * booking, and the dashboard's numbers. Nothing is generated on its own, so
 * no page can contradict another (src/test/sample-invariants.test.ts).
 */
import { addDays, eachDay, today } from "./dates";
import PACKS from "./packs.json";
import type { Booking, BookingStatus, CallRow, Correction, Customer, Export, Insights, Lexicon, PackSummary, Payment, Status, Turn, WaitlistEntry } from "./types";

// ── the packs, as the engine reads them ───────────────────────────────────
interface PackService { name: string; price_inr: number | null; duration_min: number; staff: string[]; aliases: string[] }
interface PackInfo {
  pack_id: string; display_name: string; version: number; language: string; business_name: string; agent_name: string;
  greeting: string; closing: string; staff: string[]; staff_role: string; services: PackService[];
  hours: Record<string, string[]>; knowledge: { q: string; a: string }[]; refusal_line: string; escalation_line: string;
  after_hours_line: string; emergency_contact: string;
  scenarios: number; issues: string[]; lexicon: Lexicon["entries"];
}
const ALL = (PACKS as { packs: PackInfo[] }).packs;
export function packInfo(pack: string): PackInfo { return ALL.find((p) => p.pack_id === pack) ?? ALL.find((p) => p.pack_id === "dental_clinic")!; }

export const SAMPLE_STATUS: Status = {
  name: "HaanJi demo server", version: "1.1.0", default_pack: "dental_clinic", packs: ALL.map((p) => p.pack_id),
};

/** How far the made-up history reaches. Customers' visits are counted over it. */
export const WINDOW = { pastDays: 28, futureDays: 14 };

// ── small deterministic tools ─────────────────────────────────────────────
function rng(seed: number): () => number {
  let a = seed | 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return h >>> 0;
}
const pick = <T,>(r: () => number, xs: readonly T[]): T => xs[Math.floor(r() * xs.length)]!;
function weighted<T>(r: () => number, xs: readonly (readonly [T, number])[]): T {
  const total = xs.reduce((a, [, w]) => a + w, 0);
  let x = r() * total;
  for (const [v, w] of xs) { if ((x -= w) < 0) return v; }
  return xs[xs.length - 1]![0];
}
const toMin = (hhmm: string) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));
const hhmm = (min: number) => `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;
const jsDay = (iso: string) => new Date(`${iso}T12:00:00`).getDay();
/** The pack's hours for a date: [open, close, break from, break to] in minutes, or null when closed. */
function hoursOn(p: PackInfo, iso: string): [number, number, number, number] | null {
  const h = p.hours[String((jsDay(iso) + 6) % 7)];          // packs count Monday as 0
  if (!h) return null;
  return [toMin(h[0]!), toMin(h[1]!), h[2] ? toMin(h[2]) : -1, h[3] ? toMin(h[3]) : -1];
}
const code8 = (seed: string) => hash(seed).toString(16).toUpperCase().padStart(8, "0").slice(0, 8);
const median = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor((s.length - 1) / 2)]! : 0; };

const DAYS_HI = ["Ravivaar", "Somvaar", "Mangalvaar", "Budhvaar", "Guruvaar", "Shukravaar", "Shanivaar"];
function sayTime(min: number): string {
  const h = Math.floor(min / 60), m = min % 60;
  const part = h < 12 ? "subah" : h < 16 ? "dopahar" : h < 20 ? "shaam" : "raat";
  const h12 = ((h + 11) % 12) + 1;
  return m === 30 ? `${part} saade ${h12} baje` : m === 0 ? `${part} ${h12} baje` : `${part} ${h12}:${String(m).padStart(2, "0")} baje`;
}
function sayDay(fromIso: string, toIso: string): string {
  const diff = Math.round((new Date(`${toIso}T12:00:00`).getTime() - new Date(`${fromIso}T12:00:00`).getTime()) / 86400000);
  return diff === 0 ? "aaj" : diff === 1 ? "kal" : diff === 2 ? "parso" : DAYS_HI[jsDay(toIso)]!;
}
/** How a recogniser might mishear a word: the Bhasha Bridge's job in a call. */
function mishear(word: string): string {
  return word.replace(/ee/g, "i").replace(/oo/g, "u").replace(/c(?=[aeiou])/g, "k").replace(/th/g, "t").replace(/ph/g, "f");
}

const FIRST = ["Aarav", "Aditi", "Akash", "Ananya", "Anil", "Anjali", "Arjun", "Ayesha", "Deepak", "Divya", "Farhan", "Gaurav",
  "Harsh", "Isha", "Kabir", "Kavya", "Kiran", "Lakshmi", "Manish", "Meera", "Mohit", "Naina", "Neha", "Nikhil", "Pooja",
  "Pradeep", "Priya", "Rahul", "Rajesh", "Ritu", "Rohan", "Sakshi", "Sana", "Sanjay", "Shreya", "Simran", "Sneha", "Suresh",
  "Tanvi", "Tarun", "Uma", "Varun", "Vikram", "Yash", "Zoya", "Imran", "Gurpreet", "Fatima", "Joseph", "Lalit"] as const;
const LAST = ["Sharma", "Verma", "Gupta", "Iyer", "Nair", "Khan", "Singh", "Jain", "Mehta", "Patel", "Reddy", "Das",
  "Bose", "Kulkarni", "Joshi", "Malhotra", "Chopra", "Pillai", "Sheikh", "Agarwal", "Rao", "Mishra", "Kapoor", "Desai"] as const;

// ── the shop ──────────────────────────────────────────────────────────────
interface Person { name: string; phone: string }
export interface Shop {
  pack: PackInfo;
  people: Person[];
  bookings: Booking[];          // the whole window, every status
  customers: Customer[];        // counted from `bookings`
  calls: CallRow[];             // today, newest first
  receipts: Export["receipts"]; // one per booking
  yesterdayCalls: number;       // counted the way today's are
  missed: { total: number; recovered: number };
}

const cache = new Map<string, Shop>();
/** The shop for a pack, as of `now` (the current time unless a test says otherwise). */
export function shop(packId: string, now: Date = new Date()): Shop {
  const key = `${packId}|${now.toDateString()}|${Math.floor((now.getHours() * 60 + now.getMinutes()) / 10)}`;
  let s = cache.get(key);
  if (!s) { s = build(packInfo(packId), now); cache.set(key, s); }
  return s;
}

function build(p: PackInfo, now: Date): Shop {
  const seed = hash(p.pack_id);
  const day = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const nowMin = now.getHours() * 60 + now.getMinutes();

  // 1. a hundred people who might call
  const r0 = rng(seed);
  const people: Person[] = [];
  const names = new Set<string>();
  while (people.length < 100) {
    const name = `${pick(r0, FIRST)} ${pick(r0, LAST)}`;
    if (names.has(name)) continue;
    names.add(name);
    // the first keeps the hand-made number the demo tests and README screenshots use
    people.push({ name, phone: people.length === 0 ? "98XXXXXX10" : `9${1 + Math.floor(r0() * 8)}XXXXX${String(100 + people.length * 7).slice(-3)}` });
  }

  // the first person is the demo's one known caller: one question today, nothing else
  const others_ = people.slice(1);

  // 2. bookings, day by day, inside the pack's hours, never two at once for one person on staff
  const bookings: Booking[] = [];
  for (const date of eachDay(addDays(day, -WINDOW.pastDays), addDays(day, WINDOW.futureDays))) {
    const hours = hoursOn(p, date);
    if (!hours) continue;
    const [open, close, brFrom, brTo] = hours;
    const r = rng(seed ^ hash(date));
    const free: Record<string, number> = {};
    for (const s of p.staff) free[s] = open + Math.floor(r() * 3) * 30;
    const wanted = 5 + Math.floor(r() * 7);
    for (let i = 0, tries = 0; i < wanted && tries < 40; tries++) {
      const svc = pick(r, p.services);
      const staff = pick(r, svc.staff);
      let start = Math.ceil((free[staff]! + (r() < .5 ? 0 : 30)) / 30) * 30;
      if (brFrom >= 0 && start < brTo && start + svc.duration_min > brFrom) start = brTo;
      if (start + svc.duration_min > close) continue;
      free[staff] = start + svc.duration_min;
      const person = pick(r, others_);
      const ends = start + svc.duration_min;
      let status: BookingStatus;
      if (date < day || (date === day && ends <= nowMin)) status = weighted(r, [["COMPLETED", 88], ["NO_SHOW", 8], ["CANCELLED", 4]] as const);
      else status = weighted(r, [["CONFIRMED", 95], ["CANCELLED", 5]] as const);
      // when it was booked: some today (those are today's booking calls), the rest earlier
      const bookedToday = date >= day && r() < .15;
      const leadDays = bookedToday ? 0 : 1 + Math.floor(r() * 6);
      // booked earlier means before today, never "later than today"
      let createdDay = bookedToday ? day : addDays(date, -leadDays) < day ? addDays(date, -leadDays) : addDays(day, -1 - Math.floor(r() * 3));
      const latest = date === day ? Math.min(nowMin - 2, start - 30) : nowMin - 2;   // booked before it starts, and before now
      let createdMin = createdDay === day ? 8 * 60 + Math.floor(r() * 12 * 60) : 9 * 60 + Math.floor(r() * 10 * 60);
      // A booking "made today" at a time that has not come yet was made the
      // evening before; clamping it to now piled the whole day's booking calls
      // into the minutes before now (31 calls by 00:43).
      if (createdDay === day && createdMin > latest) { createdDay = addDays(day, -1); createdMin = 19 * 60 + Math.floor(r() * 150); }
      const created = `${createdDay}T${hhmm(createdMin)}:${String(Math.floor(r() * 60)).padStart(2, "0")}`;
      const price = svc.price_inr ?? 0;
      const remindedAt = `${addDays(date, -1)}T18:00:00`;
      const id = `sample-${p.pack_id}-${date}-${i}`;
      const c = code8(id);
      bookings.push({
        booking_id: id, service: svc.name, staff, date, time: hhmm(start), duration_min: svc.duration_min,
        customer_name: person.name, phone: person.phone, status, receipt_code: `${c.slice(0, 4)}-${c.slice(4)}`,
        created_at: created, paid: price >= 2500 && r() < .6, deposit_inr: price >= 2500 ? 500 : 0, payment_link: null,
        // the evening-before reminder goes at 18:00 once that evening has come; a booking made after it
        // has its confirmation message instead, sent when it was made
        reminder_sent_at: created < remindedAt ? (remindedAt <= `${day}T${hhmm(nowMin)}` ? remindedAt : null) : created,
      });
      i++;
    }
  }
  // a booking made "today" can only be made before now
  const madeToday = bookings.filter((b) => b.created_at.startsWith(day) && b.created_at.slice(11, 16) <= hhmm(nowMin));
  for (const b of bookings) if (b.created_at.startsWith(day) && !madeToday.includes(b)) b.created_at = `${addDays(day, -1)}T19:30:00`;

  // 3. the register, counted from the calendar
  const customers: Customer[] = people.map((person) => {
    const mine = bookings.filter((b) => b.phone === person.phone);
    const done = mine.filter((b) => b.status === "COMPLETED").sort((a, b) => a.date.localeCompare(b.date));
    const latest = [...mine].filter((b) => b.status !== "CANCELLED").sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time)).pop();
    return {
      phone: person.phone, name: person.name, last_service: latest?.service ?? null,
      last_visit: done.length ? done[done.length - 1]!.date : null, visits: done.length,
      bookings: mine.filter((b) => b.status === "CONFIRMED").length, no_shows: mine.filter((b) => b.status === "NO_SHOW").length,
    };
  }).sort((a, b) => (b.last_visit ?? "").localeCompare(a.last_visit ?? "") || a.name.localeCompare(b.name));

  // 4. today's calls: one for every booking made today, then the calls that did not end in one
  const r = rng(seed ^ hash(day));
  const calls: CallRow[] = [];
  const channelOf = () => weighted(r, [["PHONE", 55], ["WHATSAPP", 40], ["WEB", 5]] as const);
  const lat = (tool: boolean) => Math.round(tool ? 140 + r() * 180 : 0.4 + r() * 2);
  const turn = (heard: string, said: string, extra: Partial<Turn> = {}): Turn =>
    ({ heard, corrected: heard, said, tools: [], speculation_hits: [], guard: null, latency_ms: lat(false), interrupted: false, corrections: [], ...extra });
  const finish = (id: string, channel: string, phone: string | null, at: string, outcome: string, turns: Turn[], receipts: string[]): CallRow => ({
    call_id: id, channel, phone, started_at: at, ended_at: at, outcome,
    corrections: turns.reduce((a, t) => a + t.corrections.length, 0),
    spec_started: turns.filter((t) => t.tools.includes("check_availability")).length,
    spec_hits: turns.filter((t) => t.speculation_hits.length > 0).length,
    latency_p50: median(turns.map((t) => t.latency_ms ?? 0)),
    turns_json: JSON.stringify(turns), receipts_json: JSON.stringify(receipts),
  });

  madeToday.forEach((b, i) => {
    const channel = channelOf();
    const ask = `mujhe ${b.service} ke liye appointment chahiye`;
    const heard = mishear(b.service);
    const corrections: Correction[] = heard !== b.service ? [{ from_token: heard, to_surface: b.service, asr_confidence: Math.round((.25 + r() * .4) * 100) / 100 }] : [];
    const dayWord = sayDay(day, b.date);
    const when = `${dayWord.length > 5 ? `${dayWord} ko` : dayWord} ${sayTime(toMin(b.time))}`;
    const hit = r() < .5;
    const whoLine = channel === "WHATSAPP" ? "Kis naam se booking karun?" : "Naam aur mobile number bata dijiye.";
    const turns: Turn[] = [
      turn(corrections.length ? ask.replace(b.service, heard) : ask, `Theek hai. ${b.service} ke liye kis din ka time dekhun?`, { corrections, corrected: ask }),
      turn(`${dayWord} ka time mil jayega`, `${when} khaali hai, ${b.staff} ke saath. Chalega?`,
           { tools: ["check_availability"], speculation_hits: hit ? ["check_availability"] : [], latency_ms: lat(true) }),
      turn("haan ji wahi theek hai", whoLine),
      turn(channel === "WHATSAPP" ? `naam ${b.customer_name.split(" ")[0]} hai` : `naam ${b.customer_name} hai, number ${b.phone}`,
           `Ek baar dohra deta hoon: ${b.service}, ${when}, ${b.staff} ke saath, ${b.customer_name} naam se. Confirm kar dun?`),
      turn("haan confirm kar do", `Ho gaya. Confirmation code ${b.receipt_code}. ${p.closing}`,
           { tools: ["book_appointment"], latency_ms: lat(true) }),
    ];
    const at = new Date(new Date(b.created_at).getTime() - 2 * 60000);
    calls.push(finish(`sample-${p.pack_id}-b${i}`, channel, b.phone, `${day}T${hhmm(at.getHours() * 60 + at.getMinutes())}:${String(at.getSeconds()).padStart(2, "0")}`, "BOOKED", turns, [b.receipt_code]));
  });

  const callStart = nowMin >= 8 * 60 ? 7 * 60 : 0;
  const atToday = () => `${day}T${hhmm(callStart + Math.floor(r() * Math.max(1, nowMin - callStart)))}:${String(Math.floor(r() * 60)).padStart(2, "0")}`;
  const closedDay = DAYS_HI.find((_, d) => !p.hours[String((d + 6) % 7)]);
  const others = Math.round(madeToday.length * 1.1) + 4;
  for (let i = 0; i < others; i++) {
    const outcome = i === 0 ? "FAQ_ANSWERED" : weighted(r, [["FAQ_ANSWERED", 45], ["LEAD_CAPTURED", 22], ["HANDED_OFF", 9], ["REFUSED", 8], ["ABANDONED", 16]] as const);
    const person = i === 0 ? people[0]! : r() < .6 ? pick(r, others_) : { name: "", phone: `9${1 + Math.floor(r() * 8)}XXXXX${String(Math.floor(r() * 900) + 100)}` };
    let turns: Turn[];
    if (outcome === "FAQ_ANSWERED" && p.knowledge.length) {
      const k = pick(r, p.knowledge);
      turns = [turn(k.q.toLowerCase().replace(/\?$/, ""), k.a), turn("theek hai dhanyavaad", p.closing)];
    } else if (outcome === "LEAD_CAPTURED") {
      const asks: [string, string][] = [
        ...(closedDay ? [[`${closedDay} ko slot milega kya`, `${closedDay} ko hum band rehte hain.`] as [string, string]] : []),
        ["shaam ko der se ka time chahiye", "Itni der ka slot abhi khaali nahi hai."],
        ["abhi busy hoon, baad mein call kar lena", "Koi baat nahi."],
        ["daam ke baare mein thoda detail mein samjhna hai", "Ye hamari team aapko theek se samjhayegi."],
        ["is hafte koi bhi slot chalega, jo khaali ho", "Is hafte ke slot team confirm karke batayegi."],
      ];
      const [ask, why] = pick(r, asks);
      turns = [turn(ask, `${why} Aapka number note kar leta hoon, team aapko call karegi.`),
               turn(`haan theek hai, naam ${person.name || "Ravi"} hai`, "Theek hai, team aapko call karegi.", { tools: ["capture_lead"] })];
    } else if (outcome === "HANDED_OFF") {
      if (r() < .45) {
        // an emergency: the engine's guardrail hands it off; out of hours it promises no transfer
        const at = atToday();
        const hours = hoursOn(p, day);
        const open = !!hours && toMin(at.slice(11, 16)) >= hours[0] && toMin(at.slice(11, 16)) < hours[1];
        const contact = p.emergency_contact ? `Emergency ho to turant ${p.emergency_contact} par sampark kijiye. ` : "Emergency ho to turant nazdeeki hospital jaaiye. ";
        turns = [turn(`haan ji ${pick(r, p.services).name} ke baare mein poochna tha`, "Zaroor. Batayiye kya hua?"),
                 turn("bahut zyada khoon aa raha hai, ruk nahi raha", open ? p.escalation_line : p.after_hours_line.replace("{contact}", contact),
                      { tools: ["handoff"], guard: "emergency.bleeding" })];
        calls.push(finish(`sample-${p.pack_id}-o${i}`, channelOf(), person.phone, at, "HANDED_OFF", turns, []));
        continue;
      }
      turns = [turn("mujhe kisi insaan se baat karni hai", "Zaroor. Main aapki baat staff tak pahuncha deta hoon; woh aapko call karenge.", { tools: ["handoff"], guard: "handoff.request" })];
    } else if (outcome === "REFUSED") {
      turns = [turn("koi discount mil jayega kya", p.refusal_line, { guard: "never_quote_outside_catalogue" })];
    } else {
      turns = [turn(`haan ji ${pick(r, p.services).name} ke baare mein`, "Zaroor. Kis din ka time dekhun?")];
    }
    calls.push(finish(`sample-${p.pack_id}-o${i}`, channelOf(), person.phone, atToday(), outcome === "FAQ_ANSWERED" && !p.knowledge.length ? "ABANDONED" : outcome, turns, []));
  }
  calls.sort((a, b) => b.started_at.localeCompare(a.started_at));

  // 5. the ledger: one sealed receipt per booking, in the order they were made
  const receipts = [...bookings].sort((a, b) => a.created_at.localeCompare(b.created_at)).map((b, i) => ({
    seq: i + 1, action: "book_appointment", short_code: b.receipt_code.replace("-", ""),
    action_args: JSON.stringify({ service: b.service, date: b.date, time: b.time, staff: b.staff }),
    occurred_at: b.created_at,
  }));

  // 6. missed calls that WhatsApp brought back: some of today's WhatsApp bookings
  const waBooked = calls.filter((c) => c.outcome === "BOOKED" && c.channel === "WHATSAPP").length;
  const recovered = Math.min(waBooked, Math.round(waBooked * .4));
  // yesterday's calls by the same rule as today's: one per booking made then, and the rest
  const madeYesterday = bookings.filter((b) => b.created_at.startsWith(addDays(day, -1))).length;
  const yesterdayCalls = madeYesterday + Math.round(madeYesterday * 1.1) + 4;
  return { pack: p, people, bookings, customers, calls, receipts, yesterdayCalls, missed: { total: recovered + Math.round(recovered * .5) + 1, recovered } };
}

/** What a call that needs the owner looks like: a lead or a hand-off. */
export const NEEDS_CALLBACK = (c: CallRow) => c.outcome === "LEAD_CAPTURED" || c.outcome === "HANDED_OFF";

/** The dashboard's numbers, counted from the shop's calls and bookings. */
export function insightsOf(s: Shop): Insights {
    const outcomes: Record<string, number> = {};
    const byHour = new Map<string, { hour: string; calls: number; booked: number }>();
    for (const c of s.calls) {
      const o = c.outcome ?? "IN_PROGRESS";
      outcomes[o] = (outcomes[o] ?? 0) + 1;
      const h = c.started_at.slice(11, 13);
      const slot = byHour.get(h) ?? { hour: h, calls: 0, booked: 0 };
      slot.calls++;
      if (o === "BOOKED") slot.booked++;
      byHour.set(h, slot);
    }
    const todays = new Set(s.calls.flatMap((c) => (c.outcome === "BOOKED" ? (JSON.parse(c.receipts_json) as string[]) : [])));
    const madeToday = s.bookings.filter((b) => todays.has(b.receipt_code));
    const revenue = madeToday.reduce((a, b) => a + (s.pack.services.find((x) => x.name === b.service)?.price_inr ?? 0), 0);
    const booked = outcomes.BOOKED ?? 0;
    const corrections = s.calls.reduce((a, c) => a + c.corrections, 0);
    const specStarted = s.calls.reduce((a, c) => a + (c.spec_started ?? 0), 0);
    const specHits = s.calls.reduce((a, c) => a + c.spec_hits, 0);
    const hours = [...byHour.values()].sort((a, b) => a.hour.localeCompare(b.hour));
    const busiest = hours.reduce((m, x) => (x.calls > m.calls ? x : m), hours[0] ?? { hour: "—", calls: 0, booked: 0 });
    const n = s.calls.length;
    return {
      tenant_id: s.pack.pack_id, generated_at: new Date().toISOString(),
      calls_total: n, calls_today: n, calls_yesterday: s.yesterdayCalls, outcomes, by_hour: hours,
      bookings_confirmed: booked, revenue_booked_inr: revenue, leads_open: s.calls.filter(NEEDS_CALLBACK).length,
      missed_calls: s.missed, corrections_total: corrections,
      speculation: { started: specStarted, hits: specHits, hit_rate: specStarted ? specHits / specStarted : 0 },
      cost: { ai_per_call_inr: 3.16, receptionist_per_call_inr: 9.23 },
      insights: [
        t("{n} calls came in today; {booked} became bookings ({pct}%).", { n, booked, pct: n ? Math.round((booked * 100) / n) : 0 }),
        t("Today's bookings are worth about ₹{revenue} at catalogue prices.", { revenue: revenue.toLocaleString("en-IN") }),
        t("{recovered} of {total} missed calls came back on WhatsApp.", { recovered: s.missed.recovered, total: s.missed.total }),
        t("Busiest hour so far: {hour}:00, {calls} calls.", { hour: busiest.hour, calls: busiest.calls }),
        t("Bhasha fixed {n} misheard words.", { n: corrections }),
        t("Sample data: a made-up day at {business}. Switch Sample off for real numbers.", { business: s.pack.business_name }),
      ],
    };
}

// ── the API the pages read ────────────────────────────────────────────────
export const sample = {
  status: SAMPLE_STATUS,

  insights(pack: string): Insights { return insightsOf(shop(pack)); },
  calls(pack: string): CallRow[] { return shop(pack).calls; },
  call(pack: string, id: string): CallRow | null { return shop(pack).calls.find((c) => c.call_id === id) ?? null; },

  export(pack: string): Export {
    return { tenant_id: pack, algorithm: "Ed25519", public_key: "", exported_at: new Date().toISOString(), receipts: shop(pack).receipts };
  },

  lexicon(pack: string): Lexicon {
    const p = packInfo(pack);
    return { pack: p.pack_id, version: p.version, entries: p.lexicon };
  },

  packs(): PackSummary[] {
    return ALL.map((p) => ({ pack_id: p.pack_id, display_name: p.display_name, version: p.version, language: p.language,
                             services: p.services.length, staff: p.staff.length, scenarios: p.scenarios, issues: p.issues }));
  },

  bookings(pack: string, from: string, to: string): Booking[] {
    return shop(pack).bookings.filter((b) => b.date >= from && b.date <= to);
  },

  customers(pack: string, query = ""): Customer[] {
    const all = shop(pack).customers;
    const needle = query.trim().toLowerCase();
    return needle ? all.filter((c) => c.name.toLowerCase().includes(needle) || c.phone.endsWith(needle)) : all;
  },

  /** People waiting for the busiest coming day, who are not already booked on it. */
  waitlist(pack: string): WaitlistEntry[] {
    const s = shop(pack);
    const coming = s.bookings.filter((b) => b.date > today() && b.status === "CONFIRMED");
    const counts = new Map<string, number>();
    for (const b of coming) counts.set(b.date, (counts.get(b.date) ?? 0) + 1);
    const busiest = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    if (!busiest) return [];
    const booked = new Set(coming.filter((b) => b.date === busiest).map((b) => b.phone));
    return s.people.filter((p) => !booked.has(p.phone)).slice(3, 5).map((p, i) => ({
      entry_id: `wl-sample-${pack}-${i}`, phone: p.phone, name: p.name, service: s.pack.services[i % s.pack.services.length]!.name,
      date: busiest, period: i ? "morning" : "evening", created_at: `${today()}T09:1${i}:00`, offered_at: null, status: "WAITING",
    }));
  },

  /** Deposit links for the bookings that ask for one. */
  payments(pack: string): Payment[] {
    return shop(pack).bookings.filter((b) => b.deposit_inr > 0 && b.status !== "CANCELLED").slice(-12).map((b): Payment => ({
      payment_id: `pay-${b.booking_id}`, booking_id: b.booking_id, amount_inr: b.deposit_inr,
      status: b.paid ? "PAID" : b.date < today() ? "EXPIRED" : "CREATED", link: `/pay/${b.booking_id}`,
      created_at: b.created_at, paid_at: b.paid ? b.created_at : null, phone: b.phone, receipt_code: b.receipt_code,
    })).sort((a, b) => b.created_at.localeCompare(a.created_at));
  },
};
