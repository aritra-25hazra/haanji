import { describe, expect, it } from "vitest";
import { NEEDS_CALLBACK, SAMPLE_STATUS, WINDOW, insightsOf, packInfo, sample, shop } from "../sample";
import type { Turn } from "../types";

// Every pack, at three moments: mid-afternoon on a weekday, a Sunday, and
// early morning (few or no calls yet). The sample shop must agree with itself
// at every one of them.
const MOMENTS = [new Date(2026, 10, 17, 15, 30), new Date(2026, 10, 22, 12, 0), new Date(2026, 10, 18, 8, 30)];
const CASES = SAMPLE_STATUS.packs.flatMap((pack) => MOMENTS.map((now) => [pack, now] as const));
const toMin = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
const median = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s[Math.floor((s.length - 1) / 2)] ?? 0; };

describe.each(CASES)("the sample shop for %s at %s", (pack, now) => {
  const s = shop(pack, now);
  const p = packInfo(pack);
  const day = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const nowMin = now.getHours() * 60 + now.getMinutes();

  it("books only the pack's own services, with the people who do them, inside its hours", () => {
    expect(s.bookings.length).toBeGreaterThan(0);
    for (const b of s.bookings) {
      const svc = p.services.find((x) => x.name === b.service);
      expect(svc, `${b.service} is not a ${pack} service`).toBeDefined();
      expect(svc!.staff).toContain(b.staff);
      expect(p.staff).toContain(b.staff);
      const h = p.hours[String((new Date(`${b.date}T12:00:00`).getDay() + 6) % 7)];
      expect(h, `${pack} is closed on ${b.date}`).toBeDefined();
      const start = toMin(b.time), end = start + b.duration_min;
      expect(start).toBeGreaterThanOrEqual(toMin(h![0]!));
      expect(end).toBeLessThanOrEqual(toMin(h![1]!));
      if (h![2]) expect(start >= toMin(h![3]!) || end <= toMin(h![2]!)).toBe(true);
      expect(b.duration_min).toBe(svc!.duration_min);
    }
  });

  it("never double-books one person on the staff", () => {
    for (const a of s.bookings) for (const b of s.bookings) {
      if (a === b || a.date !== b.date || a.staff !== b.staff) continue;
      const overlap = toMin(a.time) < toMin(b.time) + b.duration_min && toMin(b.time) < toMin(a.time) + a.duration_min;
      expect(overlap, `${a.booking_id} overlaps ${b.booking_id}`).toBe(false);
    }
  });

  it("counts each customer's visits, no-shows and bookings from the calendar", () => {
    expect(s.customers).toHaveLength(100);
    for (const c of s.customers) {
      const mine = s.bookings.filter((b) => b.phone === c.phone);
      expect(c.visits).toBe(mine.filter((b) => b.status === "COMPLETED").length);
      expect(c.no_shows).toBe(mine.filter((b) => b.status === "NO_SHOW").length);
      expect(c.bookings).toBe(mine.filter((b) => b.status === "CONFIRMED").length);
      const last = mine.filter((b) => b.status === "COMPLETED").map((b) => b.date).sort().pop() ?? null;
      expect(c.last_visit).toBe(last);
    }
  });

  it("decides today's appointments from the clock: none that has ended is still waiting, none that is waiting has its reminder pending", () => {
    for (const b of s.bookings) {
      const ended = b.date < day || (b.date === day && toMin(b.time) + b.duration_min <= nowMin);
      if (ended) expect(["COMPLETED", "NO_SHOW", "CANCELLED"]).toContain(b.status);
      else expect(["CONFIRMED", "CANCELLED"]).toContain(b.status);
      if (b.date === day && b.status === "CONFIRMED" && b.created_at < `${day}T00:00`) expect(b.reminder_sent_at).not.toBeNull();
    }
  });

  it("keeps one ledger receipt per booking, with the same codes", () => {
    expect(s.receipts).toHaveLength(s.bookings.length);
    const codes = new Set(s.receipts.map((r) => r.short_code));
    for (const b of s.bookings) expect(codes.has(b.receipt_code.replace("-", ""))).toBe(true);
  });

  it("makes no call after now, and one booking call for every booking made today", () => {
    for (const c of s.calls) expect(c.started_at.slice(0, 10) === day && c.started_at.slice(11, 16) <= `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`).toBe(true);
    const booked = s.calls.filter((c) => c.outcome === "BOOKED");
    const madeToday = s.bookings.filter((b) => b.created_at.startsWith(day));
    expect(booked).toHaveLength(madeToday.length);
  });

  it("ends every booked call in a confirmation whose code is a booking and a receipt", () => {
    const receiptCodes = new Set(s.receipts.map((r) => r.short_code));
    for (const c of s.calls.filter((x) => x.outcome === "BOOKED")) {
      const turns = JSON.parse(c.turns_json) as Turn[];
      const [code] = JSON.parse(c.receipts_json) as string[];
      expect(code).toBeDefined();
      expect(turns.length).toBeGreaterThanOrEqual(4);
      expect(turns[turns.length - 1]!.said).toContain(`Confirmation code ${code}`);
      expect(receiptCodes.has(code!.replace("-", ""))).toBe(true);
      expect(s.bookings.find((b) => b.receipt_code === code)?.phone).toBe(c.phone);
    }
  });

  it("gives a call the same numbers in the list as in its own transcript, and the detail is the same record", () => {
    for (const c of s.calls) {
      const turns = JSON.parse(c.turns_json) as Turn[];
      expect(turns.length).toBeGreaterThan(0);
      expect(c.corrections).toBe(turns.reduce((a, t) => a + t.corrections.length, 0));
      expect(c.latency_p50).toBe(median(turns.map((t) => t.latency_ms ?? 0)));
      expect(c.spec_hits).toBe(turns.filter((t) => t.speculation_hits.length > 0).length);
    }
    if (now === MOMENTS[0]) for (const c of sample.calls(pack)) expect(sample.call(pack, c.call_id)).toBe(c);
  });

  it("shows dashboard numbers that equal the lists they summarise", () => {
    const ins = insightsOf(s);
    expect(Object.values(ins.outcomes).reduce((a, b) => a + b, 0)).toBe(s.calls.length);
    expect(ins.bookings_confirmed).toBe(s.calls.filter((c) => c.outcome === "BOOKED").length);
    expect(ins.leads_open).toBe(s.calls.filter(NEEDS_CALLBACK).length);
    expect((ins.outcomes.LEAD_CAPTURED ?? 0) + (ins.outcomes.HANDED_OFF ?? 0)).toBe(s.calls.filter(NEEDS_CALLBACK).length);
    expect(ins.by_hour.reduce((a, h) => a + h.calls, 0)).toBe(s.calls.length);
    expect(ins.corrections_total).toBe(s.calls.reduce((a, c) => a + c.corrections, 0));
    const todaysCodes = new Set(s.calls.flatMap((c) => (c.outcome === "BOOKED" ? (JSON.parse(c.receipts_json) as string[]) : [])));
    const revenue = s.bookings.filter((b) => todaysCodes.has(b.receipt_code))
      .reduce((a, b) => a + (p.services.find((x) => x.name === b.service)!.price_inr ?? 0), 0);
    expect(ins.revenue_booked_inr).toBe(revenue);
  });

  it("is the same shop every time it is asked for", () => {
    const again = shop(pack, new Date(now.getTime()));
    expect(again.bookings.map((b) => b.booking_id + b.status)).toEqual(s.bookings.map((b) => b.booking_id + b.status));
    expect(again.calls.map((c) => c.call_id)).toEqual(s.calls.map((c) => c.call_id));
  });
});

describe("the sample window", () => {
  it("reaches the weeks the calendar opens on", () => {
    expect(WINDOW.pastDays).toBeGreaterThanOrEqual(21);
    expect(WINDOW.futureDays).toBeGreaterThanOrEqual(7);
  });
});

describe("the sample day follows the clock", () => {
  it.each(SAMPLE_STATUS.packs)("%s: just after midnight there are only a few calls, and mid-afternoon they are spread over the day", (pack) => {
    const late = shop(pack, new Date(2026, 10, 18, 0, 43));
    expect(late.calls.filter((c) => c.outcome === "BOOKED")).toHaveLength(0);
    expect(late.calls.length).toBeLessThanOrEqual(6);
    const day = shop(pack, new Date(2026, 10, 17, 15, 30));
    const hours = new Set(day.calls.map((c) => c.started_at.slice(11, 13)));
    expect(hours.size).toBeGreaterThanOrEqual(4);
  });
});

describe.each(SAMPLE_STATUS.packs)("the sample queue for %s", (pack) => {
  it("agrees with today's calendar: every booking is either holding a token or still to check in, once", () => {
    const q = sample.queue(pack);
    const todays = sample.bookings(pack, q.day, q.day).filter((b) => b.status !== "CANCELLED").map((b) => b.booking_id).sort();
    const tokens = q.lines.flatMap((l) => [...(l.serving ? [l.serving] : []), ...l.waiting]);
    const counted = q.lines.reduce((n, l) => n + l.done + l.no_show, 0) + tokens.filter((t) => t.booking_id).length + q.to_check_in.length;
    expect(counted).toBe(todays.length);                                     // every booking once
    for (const b of q.to_check_in) expect(todays).toContain(b.booking_id);
    for (const t of tokens.filter((x) => x.booking_id)) expect(todays).toContain(t.booking_id);
    expect(new Set(tokens.map((t) => t.label)).size).toBe(tokens.length);
    for (const l of q.lines) expect(l.serving === null || l.serving.status === "serving").toBe(true);
  });
});
