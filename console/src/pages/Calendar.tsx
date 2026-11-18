import { useState, type CSSProperties } from "react";
import { engine, enginePath } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { en, t, tn, useT } from "../i18n";
import { Chip, Confirm, Empty, Icon, Loading, NotLive, Page, Panel, Register, fmtDate, fmtInr, fmtTime, useData, type ChipKind } from "../components/Common";
import { addDays, dayName, dayOfWeek, fmtDay, today, weekOf } from "../dates";
import type { Booking, BookingFilter, BookingStatus, Payment, WaitlistEntry } from "../types";

type View = "day" | "week";
type Action = "cancel" | Exclude<BookingStatus, "CANCELLED">;

const STATUS_LABEL: Record<BookingStatus, string> = { CONFIRMED: en("confirmed"), CANCELLED: en("cancelled"), NO_SHOW: en("no-show"), COMPLETED: en("completed") };
const STATUS_KIND: Record<BookingStatus, ChipKind | undefined> = { CONFIRMED: undefined, CANCELLED: "bad", NO_SHOW: "warn", COMPLETED: "ok" };
const FILTERS: [BookingFilter, string][] = [["ALL", en("All")], ["CONFIRMED", en("Confirmed")], ["COMPLETED", en("Completed")], ["NO_SHOW", en("No-show")], ["CANCELLED", en("Cancelled")]];
const WAIT_KIND: Record<string, ChipKind | undefined> = { WAITING: "warn", OFFERED: "ink", BOOKED: "ok", EXPIRED: "muted" };
const PAY_KIND: Record<string, ChipKind | undefined> = { CREATED: "warn", PAID: "ok", FAILED: "bad", EXPIRED: "muted" };

/** Mock payment links are relative to the engine; real ones are absolute. */
const linkHref = (l: string) => (l.startsWith("/") ? enginePath(l) : l);
const byTime = (a: Booking, b: Booking) => a.time.localeCompare(b.time);

/** The receptionist's book: a day by staff, or a week by day. */
export default function Calendar() {
  const { pack, mode, readOnly } = useApp();
  useT();
  const [view, setView] = useState<View>("day");
  const [anchor, setAnchor] = useState<string>(today);
  const [now] = useState<string>(today);
  const [filter, setFilter] = useState<BookingFilter>("ALL");
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const days = view === "day" ? [anchor] : weekOf(anchor);
  const from = days[0] ?? anchor, to = days[days.length - 1] ?? anchor;
  const live = mode === "live";
  const loader = live
    ? () => engine.bookings(pack, from, to, filter)
    : mode === "demo"
      ? () => Promise.resolve(sample.bookings(pack, from, to).filter((b) => filter === "ALL" || b.status === filter))
      : null;
  const { data, loading, error, reload } = useData(loader, [pack, mode, from, to, filter]);

  if (!live && mode !== "demo") return <NotLive title={t("Calendar")} sub={t("Every booking for the day or week, by staff.")} kind="staff" />;

  const act = async (b: Booking, what: Action) => {
    if (!live) { setNote(t("This is a sample calendar; nothing changes here.")); return; }
    setBusy(b.booking_id); setNote(null);
    try {
      if (what === "cancel") {
        await engine.cancelBooking(pack, b.booking_id);
        setNote(t("Cancelled · {name}, {time}. If someone is on the waitlist, they will be offered the slot.", { name: b.customer_name, time: b.time }));
      } else {
        await engine.setBookingStatus(pack, b.booking_id, what);
        setNote(`${b.customer_name} · ${t(STATUS_LABEL[what])}`);
      }
      reload();
    } catch (e) { setNote(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };
  const step = (n: number) => setAnchor((a) => addDays(a, view === "day" ? n : 7 * n));
  const sub = view === "day" ? fmtDay(anchor) : `${fmtDay(from)} – ${fmtDay(to)}`;

  const nav = (
    <div className="cal-nav">
      <div className="seg" role="group" aria-label={t("View")}>
        <button type="button" aria-pressed={view === "day"} onClick={() => setView("day")}>{t("Day")}</button>
        <button type="button" aria-pressed={view === "week"} onClick={() => setView("week")}>{t("Week")}</button>
      </div>
      <button className="btn btn-ghost btn-sm" onClick={() => step(-1)} aria-label={view === "day" ? t("Previous day") : t("Previous week")}><Icon name="back" small /></button>
      <button className="btn btn-ghost btn-sm" onClick={() => setAnchor(today())}>{t("Today")}</button>
      <button className="btn btn-ghost btn-sm" onClick={() => step(1)} aria-label={view === "day" ? t("Next day") : t("Next week")}><Icon name="arrow" small /></button>
      <input className="input" type="date" value={anchor} onChange={(e) => { if (e.target.value) setAnchor(e.target.value); }} aria-label={t("Pick a date")} />
      <select className="input" value={filter} onChange={(e) => setFilter(e.target.value as BookingFilter)} aria-label={t("Status filter")}>
        {FILTERS.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}
      </select>
    </div>
  );

  return (
    <Page title={t("Calendar")} sub={sub} actions={nav}>
      {note && <div className="banner" role="status"><Icon name="check" small />{note}</div>}
      <Panel title={view === "day" ? t("Day, by staff") : t("Week")} hint={data ? tn("{n} booking", "{n} bookings", data.length) : ""}
             actions={<button className="btn btn-ghost btn-sm" onClick={reload} disabled={loading}><Icon name="refresh" small />{t("Refresh")}</button>}>
        {loading && !data ? <Loading kind={view === "day" ? "staff" : "panel"} />
          : !data ? <Empty>{t("Could not load: {error}", { error: error ?? "" })}<button className="btn btn-ghost btn-sm" onClick={reload}>{t("Try again")}</button></Empty>
          : view === "day"
            ? <DayGrid bookings={data} busy={busy} onAct={act} readOnly={readOnly} />
            : <>
                <TimeGrid days={days} today={now} bookings={data} onPick={(d) => { setAnchor(d); setView("day"); }} />
                <WeekGrid days={days} today={now} bookings={data} busy={busy} onAct={act} readOnly={readOnly} />
              </>}
      </Panel>
      <WaitlistPanel pack={pack} live={live} />
      <PaymentsPanel pack={pack} live={live} />
    </Page>
  );
}

function DayGrid({ bookings, busy, onAct, readOnly = false }: { bookings: Booking[]; busy: string | null; onAct: (b: Booking, a: Action) => void; readOnly?: boolean }) {
  const byStaff = new Map<string, Booking[]>();
  for (const b of bookings) byStaff.set(b.staff, [...(byStaff.get(b.staff) ?? []), b]);
  const staffs = [...byStaff.keys()].sort();
  if (staffs.length === 0) return <Empty><p>{t("No bookings on this day.")}</p></Empty>;
  return (
    <div className="cal-grid" style={{ "--cols": staffs.length } as CSSProperties}>
      {staffs.map((s) => {
        const list = [...(byStaff.get(s) ?? [])].sort(byTime);
        return (
          <section key={s} className="cal-col" aria-label={s}>
            <h3><span>{s}</span><span className="count">{list.length}</span></h3>
            {list.map((b) => <BookingCard key={b.booking_id} b={b} busy={busy === b.booking_id} onAct={(a) => onAct(b, a)} readOnly={readOnly} />)}
          </section>
        );
      })}
    </div>
  );
}

function WeekGrid({ days, today: now, bookings, busy, onAct, readOnly = false }:
  { days: string[]; today: string; bookings: Booking[]; busy: string | null; onAct: (b: Booking, a: Action) => void; readOnly?: boolean }) {
  return (
    <div className="cal-grid week-list" style={{ "--cols": 7 } as CSSProperties}>
      {days.map((d) => {
        const list = bookings.filter((b) => b.date === d).sort(byTime);
        return (
          <section key={d} className={"cal-col" + (d === now ? " today" : "")} aria-label={fmtDay(d)}>
            <h3><span>{dayName(dayOfWeek(d))} {d.slice(8)}</span><span className="count">{list.length || ""}</span></h3>
            {list.length === 0
              ? <p className="none">—</p>
              : list.map((b) => <BookingCard key={b.booking_id} b={b} showStaff busy={busy === b.booking_id} onAct={(a) => onAct(b, a)} readOnly={readOnly} />)}
          </section>
        );
      })}
    </div>
  );
}

const STAFF_COLOURS = ["#1B3B8C", "#1F6B45", "#8A6100", "#B8371F", "#5B3FA0", "#0E7490"];
const ROW = 22;                                    // px for 30 minutes
const minutes = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));

/** The week as a time grid: a column per day, a row per half hour, a lane
 *  and a colour per person on the staff, so two bookings at one time sit
 *  side by side. A booking opens its day, where the desk can act on it.
 *  On a phone the list layout below takes its place. */
function TimeGrid({ days, today: now, bookings, onPick }:
  { days: string[]; today: string; bookings: Booking[]; onPick: (day: string) => void }) {
  const shown = bookings.filter((b) => b.status !== "CANCELLED");
  const staff = [...new Set(bookings.map((b) => b.staff))].sort();
  const from = Math.floor(Math.min(9 * 60, ...shown.map((b) => minutes(b.time))) / 60) * 60;
  const to = Math.ceil(Math.max(19 * 60, ...shown.map((b) => minutes(b.time) + b.duration_min)) / 60) * 60;
  const rows = (to - from) / 30;
  const colour = (s: string) => STAFF_COLOURS[staff.indexOf(s) % STAFF_COLOURS.length];
  return (
    <div className="time-grid" aria-label={t("The week as a time grid")}>
      {staff.length > 0 && <p className="tg-legend">{staff.map((s) => <span key={s}><i style={{ background: colour(s) }} />{s}</span>)}</p>}
      <div className="tg" style={{ "--days": days.length } as CSSProperties}>
        <div className="tg-hours" style={{ height: rows * ROW + 34 }}>
          {Array.from({ length: (to - from) / 60 + 1 }, (_, i) => (
            <span key={i} style={{ top: 34 + i * 2 * ROW }}>{String((from / 60) + i).padStart(2, "0")}:00</span>))}
        </div>
        {days.map((d) => (
          <div key={d} className={"tg-day" + (d === now ? " today" : "")}>
            <button type="button" className="tg-head" onClick={() => onPick(d)}>{dayName(dayOfWeek(d))} {d.slice(8)}</button>
            <div className="tg-body" style={{ height: rows * ROW }}>
              {shown.filter((b) => b.date === d).map((b) => {
                const lane = Math.max(0, staff.indexOf(b.staff));
                return (
                  <button type="button" key={b.booking_id} className={"tg-bk " + b.status}
                          style={{ top: ((minutes(b.time) - from) / 30) * ROW, height: Math.max(ROW, (b.duration_min / 30) * ROW) - 2,
                                   left: `calc(${(lane / staff.length) * 100}% + 1px)`, width: `calc(${100 / staff.length}% - 2px)`,
                                   "--c": colour(b.staff) } as CSSProperties}
                          title={`${b.time} · ${b.service} · ${b.customer_name} · ${b.staff}`} onClick={() => onPick(d)}>
                    <b>{b.time}</b> {b.service}<span>{b.customer_name}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** One booking: service, time, customer, receipt, money, reminder — and what
 *  the desk can do about it. Cancel asks once, inline. */
function BookingCard({ b, showStaff = false, busy, onAct, readOnly = false }: { b: Booking; showStaff?: boolean; busy: boolean; onAct: (a: Action) => void; readOnly?: boolean }) {
  const [confirm, setConfirm] = useState(false);
  useT();
  return (
    <article className={"bk " + b.status} aria-label={`${b.time} ${b.service}, ${b.customer_name}`} data-testid={`booking-${b.booking_id}`}>
      <div className="top">
        <span className="time">{b.time} · {b.duration_min} min</span>
        {b.status !== "CONFIRMED" && <Chip kind={STATUS_KIND[b.status]}>{t(STATUS_LABEL[b.status])}</Chip>}
      </div>
      <div className="svc">{b.service}{showStaff && <span className="muted"> · {b.staff}</span>}</div>
      <div className="who"><span>{b.customer_name}</span><span className="mono">{b.phone}</span></div>
      <div className="chips">
        <Chip mono title={t("receipt code")}><Icon name="lock" small />{b.receipt_code}</Chip>
        {b.paid
          ? <Chip kind="ok" title={t("paid")}><Icon name="check" small />{t("paid")}{b.deposit_inr ? ` ${fmtInr(b.deposit_inr)}` : ""}</Chip>
          : b.deposit_inr > 0
            ? <Chip kind="warn" title={t("deposit due")}><Icon name="rupee" small />{t("{amount} due", { amount: fmtInr(b.deposit_inr) })}</Chip>
            : <Chip kind="muted">{t("no deposit")}</Chip>}
        {b.payment_link && !b.paid && <a className="chip" href={linkHref(b.payment_link)} target="_blank" rel="noopener noreferrer">{t("pay link")}<Icon name="external" small /></a>}
        {b.reminder_sent_at
          ? <Chip kind="ok" title={b.reminder_sent_at}><Icon name="bell" small />{t("reminder {time}", { time: fmtTime(b.reminder_sent_at) })}</Chip>
          : b.status === "CONFIRMED" ? <Chip kind="muted"><Icon name="bell" small />{t("reminder pending")}</Chip> : null}
      </div>
      {readOnly ? (
        <div className="acts"><Chip kind="muted" title={t("This is the public demo, so bookings cannot be changed here. A shop's own console, with sign-in, can.")}>{t("Demo: changes are switched off")}</Chip></div>
      ) : confirm ? (
        <Confirm text={t("Cancel for sure? The caller gets a WhatsApp message (if the number is connected) and the free slot is offered to the waitlist.")} yes={t("Yes, cancel")} no={t("No")} busy={busy}
                 onYes={() => { setConfirm(false); onAct("cancel"); }} onNo={() => setConfirm(false)} />
      ) : (
        <div className="acts">
          {b.status === "CONFIRMED" && (
            <>
              <button className="btn btn-ghost" onClick={() => onAct("COMPLETED")} disabled={busy}><Icon name="check" small />{t("Completed")}</button>
              <button className="btn btn-ghost" onClick={() => onAct("NO_SHOW")} disabled={busy}>{t("No-show")}</button>
              <button className="btn btn-ghost" style={{ color: "var(--sindoor-ink)" }} onClick={() => setConfirm(true)} disabled={busy}>{t("Cancel")}</button>
            </>
          )}
          {(b.status === "NO_SHOW" || b.status === "COMPLETED") && (
            <button className="btn btn-ghost" onClick={() => onAct("CONFIRMED")} disabled={busy}>{t("Back to confirmed")}</button>
          )}
        </div>
      )}
    </article>
  );
}

/** People waiting for a day that was full. The engine fills and drains this
 *  itself; the desk only removes an entry that no longer applies. */
function WaitlistPanel({ pack, live }: { pack: string; live: boolean }) {
  const { data, error, reload } = useData<WaitlistEntry[]>(live ? () => engine.waitlist(pack) : () => Promise.resolve(sample.waitlist(pack)), [pack, live]);
  const [removing, setRemoving] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  useT();
  const remove = async (id: string) => {
    if (!live) { setNote(t("This is a sample waitlist; nothing changes here.")); setRemoving(null); return; }
    setBusy(true); setNote(null);
    try { await engine.removeWaitlist(pack, id); setNote(t("Removed from the waitlist.")); reload(); }
    catch (e) { setNote(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); setRemoving(null); }
  };
  const rows = data ?? [];
  const waiting = rows.filter((w) => w.status === "WAITING" || w.status === "OFFERED").length;
  return (
    <Panel title={t("Waitlist")} hint={data ? t("{n} waiting", { n: waiting }) : error ? t("could not load: {error}", { error }) : ""}>
      {rows.length === 0 ? (
        <Empty><p>{t("Nobody is waiting. When a day is full and a caller leaves a number, they show up here, and get the slot when someone cancels.")}</p></Empty>
      ) : (
        <Register head={<><th>{t("Name")}</th><th>{t("Phone")}</th><th>{t("Service")}</th><th>{t("Day")}</th><th>{t("Period")}</th><th>{t("Status")}</th><th></th></>}>
          {rows.map((w) => (
            <tr key={w.entry_id}>
              <td><strong>{w.name || "—"}</strong></td>
              <td className="mono">{w.phone}</td>
              <td>{w.service}</td>
              <td className="mono">{fmtDate(w.date)}</td>
              <td>{w.period}</td>
              <td><Chip kind={WAIT_KIND[w.status]}>{w.status.toLowerCase()}{w.offered_at ? ` · ${fmtTime(w.offered_at)}` : ""}</Chip></td>
              <td className="right">
                {removing === w.entry_id
                  ? <Confirm text={t("Remove from the waitlist?")} yes={t("Yes, remove")} busy={busy} onYes={() => void remove(w.entry_id)} onNo={() => setRemoving(null)} />
                  : <button className="btn btn-ghost btn-sm" onClick={() => setRemoving(w.entry_id)} disabled={busy}>{t("Remove")}</button>}
              </td>
            </tr>
          ))}
        </Register>
      )}
      {note && <p className="muted" role="status" style={{ padding: "10px 18px" }}>{note}</p>}
    </Panel>
  );
}

/** Payment links the engine issued, and what became of them. */
function PaymentsPanel({ pack, live }: { pack: string; live: boolean }) {
  const { data, error } = useData<Payment[]>(live ? () => engine.payments(pack) : () => Promise.resolve(sample.payments(pack)), [pack, live]);
  const rows = [...(data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const paid = rows.filter((p) => p.status === "PAID").reduce((a, p) => a + p.amount_inr, 0);
  useT();
  return (
    <Panel title={t("Payments")} hint={data ? tn("{n} link · {amount} received", "{n} links · {amount} received", rows.length, { amount: fmtInr(paid) }) : error ? t("could not load: {error}", { error }) : ""}>
      {rows.length === 0 ? (
        <Empty><p>{t("No payment links yet. Set a deposit in Settings, and every new booking gets a link.")}</p></Empty>
      ) : (
        <Register head={<><th>{t("When")}</th><th>{t("Booking")}</th><th className="right">₹</th><th>{t("Status")}</th><th>{t("Link")}</th></>}>
          {rows.map((p) => (
            <tr key={p.payment_id}>
              <td className="mono">{fmtDate(p.created_at)} {fmtTime(p.created_at)}</td>
              <td className="mono">{p.receipt_code ? <>{p.receipt_code}{p.phone && <span className="muted"> · {p.phone}</span>}</> : p.booking_id}</td>
              <td className="num right">{fmtInr(p.amount_inr)}</td>
              <td><Chip kind={PAY_KIND[p.status]}>{p.status.toLowerCase()}{p.paid_at ? ` · ${fmtTime(p.paid_at)}` : ""}</Chip></td>
              <td>{p.link ? <a href={linkHref(p.link)} target="_blank" rel="noopener noreferrer">{t("open")} <Icon name="external" small /></a> : "—"}</td>
            </tr>
          ))}
        </Register>
      )}
    </Panel>
  );
}
