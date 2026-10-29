/**
 * Calendar arithmetic on YYYY-MM-DD strings in the browser's local time —
 * never through toISOString(), which would move an IST midnight to the day
 * before. Pure, so the calendar's ranges are unit-tested.
 */
const pad = (n: number) => String(n).padStart(2, "0");

export function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y ?? 1970, (m ?? 1) - 1, d ?? 1);
}

export function isoDay(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function today(): string { return isoDay(new Date()); }

export function addDays(iso: string, n: number): string {
  const d = parseDay(iso);
  d.setDate(d.getDate() + n);
  return isoDay(d);
}

/** Monday to Sunday around a day. */
export function weekOf(iso: string): string[] {
  const dow = (parseDay(iso).getDay() + 6) % 7;
  const mon = addDays(iso, -dow);
  return Array.from({ length: 7 }, (_, i) => addDays(mon, i));
}

/** Every day from `from` to `to` inclusive (capped at two months). */
export function eachDay(from: string, to: string): string[] {
  const out: string[] = [];
  let d = from;
  for (let i = 0; d <= to && i < 62; i++) { out.push(d); d = addDays(d, 1); }
  return out;
}

export function dayOfWeek(iso: string): number { return parseDay(iso).getDay(); }

export const DAY_NAMES = ["Ravi", "Som", "Mangal", "Budh", "Guru", "Shukra", "Shani"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Guru 29 Oct" */
export function fmtDay(iso: string): string {
  const d = parseDay(iso);
  return `${DAY_NAMES[d.getDay()] ?? ""} ${d.getDate()} ${MONTHS[d.getMonth()] ?? ""}`;
}
