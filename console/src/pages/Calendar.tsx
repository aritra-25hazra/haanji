import { useState, type CSSProperties } from "react";
import { engine, enginePath } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Chip, Confirm, Empty, Icon, Loading, NotLive, Page, Panel, Register, fmtDate, fmtInr, fmtTime, useData, type ChipKind } from "../components/Common";
import { DAY_NAMES, addDays, dayOfWeek, fmtDay, today, weekOf } from "../dates";
import type { Booking, BookingFilter, BookingStatus, Payment, WaitlistEntry } from "../types";

type View = "day" | "week";
type Action = "cancel" | Exclude<BookingStatus, "CANCELLED">;

const STATUS_LABEL: Record<BookingStatus, string> = { CONFIRMED: "confirmed", CANCELLED: "cancelled", NO_SHOW: "no-show", COMPLETED: "completed" };
const STATUS_KIND: Record<BookingStatus, ChipKind | undefined> = { CONFIRMED: undefined, CANCELLED: "bad", NO_SHOW: "warn", COMPLETED: "ok" };
const FILTERS: [BookingFilter, string][] = [["ALL", "Sab"], ["CONFIRMED", "Confirmed"], ["COMPLETED", "Completed"], ["NO_SHOW", "No-show"], ["CANCELLED", "Cancelled"]];
const WAIT_KIND: Record<string, ChipKind | undefined> = { WAITING: "warn", OFFERED: "ink", BOOKED: "ok", EXPIRED: "muted" };
const PAY_KIND: Record<string, ChipKind | undefined> = { CREATED: "warn", PAID: "ok", FAILED: "bad", EXPIRED: "muted" };

/** Mock payment links are relative to the engine; real ones are absolute. */
const linkHref = (l: string) => (l.startsWith("/") ? enginePath(l) : l);
const byTime = (a: Booking, b: Booking) => a.time.localeCompare(b.time);

/** The receptionist's book: a day by staff, or a week by day. */
export default function Calendar() {
  const { pack, mode, readOnly } = useApp();
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
      ? () => Promise.resolve(sample.bookings(from, to).filter((b) => filter === "ALL" || b.status === filter))
      : null;
  const { data, loading, error, reload } = useData(loader, [pack, mode, from, to, filter]);

  if (!live && mode !== "demo") return <NotLive title="Calendar" sub="Din ya hafta — har booking, staff ke hisaab se." />;

  const act = async (b: Booking, what: Action) => {
    if (!live) { setNote("Sample calendar — yahan badlaav nahi hota."); return; }
    setBusy(b.booking_id); setNote(null);
    try {
      if (what === "cancel") {
        await engine.cancelBooking(pack, b.booking_id);
        setNote(`Cancel ho gaya · ${b.customer_name}, ${b.time}. Waitlist mein koi ho to usse slot offer hoga.`);
      } else {
        await engine.setBookingStatus(pack, b.booking_id, what);
        setNote(`${b.customer_name} · ${STATUS_LABEL[what]}`);
      }
      reload();
    } catch (e) { setNote(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };
  const step = (n: number) => setAnchor((a) => addDays(a, view === "day" ? n : 7 * n));
  const sub = view === "day" ? fmtDay(anchor) : `${fmtDay(from)} – ${fmtDay(to)}`;

  const nav = (
    <div className="cal-nav">
      <div className="seg" role="group" aria-label="View">
        <button type="button" aria-pressed={view === "day"} onClick={() => setView("day")}>Din</button>
        <button type="button" aria-pressed={view === "week"} onClick={() => setView("week")}>Hafta</button>
      </div>
      <button className="btn btn-ghost btn-sm" onClick={() => step(-1)} aria-label={view === "day" ? "Pichhla din" : "Pichhla hafta"}><Icon name="back" small /></button>
      <button className="btn btn-ghost btn-sm" onClick={() => setAnchor(today())}>Aaj</button>
      <button className="btn btn-ghost btn-sm" onClick={() => step(1)} aria-label={view === "day" ? "Agla din" : "Agla hafta"}><Icon name="arrow" small /></button>
      <input className="input" type="date" value={anchor} onChange={(e) => { if (e.target.value) setAnchor(e.target.value); }} aria-label="Date chuno" />
      <select className="input" value={filter} onChange={(e) => setFilter(e.target.value as BookingFilter)} aria-label="Status filter">
        {FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  );

  return (
    <Page title="Calendar" sub={sub} actions={nav}>
      {note && <div className="banner" role="status"><Icon name="check" small />{note}</div>}
      <Panel title={view === "day" ? "Din, staff ke hisaab se" : "Hafta"} hint={data ? `${data.length} bookings` : ""}
             actions={<button className="btn btn-ghost btn-sm" onClick={reload} disabled={loading}><Icon name="refresh" small />Refresh</button>}>
        {loading && !data ? <Loading />
          : !data ? <Empty>Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty>
          : view === "day"
            ? <DayGrid bookings={data} busy={busy} onAct={act} readOnly={readOnly} />
            : <WeekGrid days={days} today={now} bookings={data} busy={busy} onAct={act} readOnly={readOnly} />}
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
  if (staffs.length === 0) return <Empty><p>Is din koi booking nahi.</p></Empty>;
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
    <div className="cal-grid" style={{ "--cols": 7 } as CSSProperties}>
      {days.map((d) => {
        const list = bookings.filter((b) => b.date === d).sort(byTime);
        return (
          <section key={d} className={"cal-col" + (d === now ? " today" : "")} aria-label={fmtDay(d)}>
            <h3><span>{DAY_NAMES[dayOfWeek(d)]} {d.slice(8)}</span><span className="count">{list.length || ""}</span></h3>
            {list.length === 0
              ? <p className="none">—</p>
              : list.map((b) => <BookingCard key={b.booking_id} b={b} showStaff busy={busy === b.booking_id} onAct={(a) => onAct(b, a)} readOnly={readOnly} />)}
          </section>
        );
      })}
    </div>
  );
}

/** One booking: service, time, customer, receipt, money, reminder — and what
 *  the desk can do about it. Cancel asks once, inline. */
function BookingCard({ b, showStaff = false, busy, onAct, readOnly = false }: { b: Booking; showStaff?: boolean; busy: boolean; onAct: (a: Action) => void; readOnly?: boolean }) {
  const [confirm, setConfirm] = useState(false);
  return (
    <article className={"bk " + b.status} aria-label={`${b.time} ${b.service} — ${b.customer_name}`} data-testid={`booking-${b.booking_id}`}>
      <div className="top">
        <span className="time">{b.time} · {b.duration_min} min</span>
        {b.status !== "CONFIRMED" && <Chip kind={STATUS_KIND[b.status]}>{STATUS_LABEL[b.status]}</Chip>}
      </div>
      <div className="svc">{b.service}{showStaff && <span className="muted"> · {b.staff}</span>}</div>
      <div className="who"><span>{b.customer_name}</span><span className="mono">{b.phone}</span></div>
      <div className="chips">
        <Chip mono title="receipt code"><Icon name="lock" small />{b.receipt_code}</Chip>
        {b.paid
          ? <Chip kind="ok" title="paid"><Icon name="check" small />paid{b.deposit_inr ? ` ${fmtInr(b.deposit_inr)}` : ""}</Chip>
          : b.deposit_inr > 0
            ? <Chip kind="warn" title="deposit baaki"><Icon name="rupee" small />{fmtInr(b.deposit_inr)} baaki</Chip>
            : <Chip kind="muted">no deposit</Chip>}
        {b.payment_link && !b.paid && <a className="chip" href={linkHref(b.payment_link)} target="_blank" rel="noopener noreferrer">pay link<Icon name="external" small /></a>}
        {b.reminder_sent_at
          ? <Chip kind="ok" title={b.reminder_sent_at}><Icon name="bell" small />reminder {fmtTime(b.reminder_sent_at)}</Chip>
          : b.status === "CONFIRMED" ? <Chip kind="muted"><Icon name="bell" small />reminder pending</Chip> : null}
      </div>
      {readOnly ? (
        <div className="acts"><Chip kind="muted" title="Public demo: badlav band hain. Asli dukaan ke liye HAANJI_AUTH=on.">demo · read-only</Chip></div>
      ) : confirm ? (
        <Confirm text="Pakka cancel karein? Caller ko WhatsApp par suchna jayegi (agar number juda hai) aur khaali slot waitlist wale ko offer hoga." yes="Haan, cancel karo" no="Nahi" busy={busy}
                 onYes={() => { setConfirm(false); onAct("cancel"); }} onNo={() => setConfirm(false)} />
      ) : (
        <div className="acts">
          {b.status === "CONFIRMED" && (
            <>
              <button className="btn btn-ghost" onClick={() => onAct("COMPLETED")} disabled={busy}><Icon name="check" small />Completed</button>
              <button className="btn btn-ghost" onClick={() => onAct("NO_SHOW")} disabled={busy}>No-show</button>
              <button className="btn btn-ghost" style={{ color: "var(--sindoor-ink)" }} onClick={() => setConfirm(true)} disabled={busy}>Cancel</button>
            </>
          )}
          {(b.status === "NO_SHOW" || b.status === "COMPLETED") && (
            <button className="btn btn-ghost" onClick={() => onAct("CONFIRMED")} disabled={busy}>Wapas confirmed</button>
          )}
        </div>
      )}
    </article>
  );
}

/** People waiting for a day that was full. The engine fills and drains this
 *  itself; the desk only removes an entry that no longer applies. */
function WaitlistPanel({ pack, live }: { pack: string; live: boolean }) {
  const { data, error, reload } = useData<WaitlistEntry[]>(live ? () => engine.waitlist(pack) : () => Promise.resolve(sample.waitlist()), [pack, live]);
  const [removing, setRemoving] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const remove = async (id: string) => {
    if (!live) { setNote("Sample waitlist — yahan badlaav nahi hota."); setRemoving(null); return; }
    setBusy(true); setNote(null);
    try { await engine.removeWaitlist(pack, id); setNote("Waitlist se hata diya."); reload(); }
    catch (e) { setNote(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); setRemoving(null); }
  };
  const rows = data ?? [];
  const waiting = rows.filter((w) => w.status === "WAITING" || w.status === "OFFERED").length;
  return (
    <Panel title="Waitlist" hint={data ? `${waiting} intezaar mein` : error ? `load nahi hua: ${error}` : ""}>
      {rows.length === 0 ? (
        <Empty><p>Koi intezaar mein nahi. Din full ho aur caller number chhode, to woh yahan aata hai — aur cancel pe usse slot milta hai.</p></Empty>
      ) : (
        <Register head={<><th>Naam</th><th>Phone</th><th>Service</th><th>Din</th><th>Period</th><th>Status</th><th></th></>}>
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
                  ? <Confirm text="Waitlist se hatao?" yes="Haan, hatao" busy={busy} onYes={() => void remove(w.entry_id)} onNo={() => setRemoving(null)} />
                  : <button className="btn btn-ghost btn-sm" onClick={() => setRemoving(w.entry_id)} disabled={busy}>Hatao</button>}
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
  const { data, error } = useData<Payment[]>(live ? () => engine.payments(pack) : () => Promise.resolve(sample.payments()), [pack, live]);
  const rows = data ?? [];
  const paid = rows.filter((p) => p.status === "PAID").reduce((a, p) => a + p.amount_inr, 0);
  return (
    <Panel title="Payments" hint={data ? `${rows.length} links · ${fmtInr(paid)} aaya` : error ? `load nahi hua: ${error}` : ""}>
      {rows.length === 0 ? (
        <Empty><p>Abhi koi payment link nahi. Settings mein deposit set karo — har nayi booking pe link jayega.</p></Empty>
      ) : (
        <Register head={<><th>Kab</th><th>Booking</th><th className="right">₹</th><th>Status</th><th>Link</th></>}>
          {rows.map((p) => (
            <tr key={p.payment_id}>
              <td className="mono">{fmtDate(p.created_at)} {fmtTime(p.created_at)}</td>
              <td className="mono">{p.booking_id}</td>
              <td className="num right">{fmtInr(p.amount_inr)}</td>
              <td><Chip kind={PAY_KIND[p.status]}>{p.status.toLowerCase()}{p.paid_at ? ` · ${fmtTime(p.paid_at)}` : ""}</Chip></td>
              <td>{p.link ? <a href={linkHref(p.link)} target="_blank" rel="noopener noreferrer">kholo <Icon name="external" small /></a> : "—"}</td>
            </tr>
          ))}
        </Register>
      )}
    </Panel>
  );
}
