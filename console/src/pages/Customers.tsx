import { useEffect, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { addDays, today } from "../dates";
import { engine } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Chip, Confirm, Empty, Icon, Loading, NotLive, Page, Panel, Register, fmtDate, fmtTime, rowButton, useData, type ChipKind } from "../components/Common";
import type { Booking, CallRow, Customer } from "../types";
import { outcomeLabel } from "../labels";
import { t, tn, useT } from "../i18n";

/** One customer's bookings and calls, from the same lists the Calendar and
 *  Calls pages read (a public demo masks the number the same way in each). */
async function history(pack: string, phone: string, live: boolean): Promise<{ bookings: Booking[]; calls: CallRow[] }> {
  const from = addDays(today(), -120), to = addDays(today(), 60);
  const [bookings, calls] = live
    ? await Promise.all([engine.bookings(pack, from, to), engine.calls(pack, 500).then((r) => r.conversations)])
    : [sample.bookings(pack, from, to), sample.calls(pack)];
  return { bookings: bookings.filter((b) => b.phone === phone).sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time)),
           calls: calls.filter((x) => x.phone === phone) };
}

const BK_KIND: Record<string, ChipKind | undefined> = { CONFIRMED: undefined, COMPLETED: "ok", NO_SHOW: "warn", CANCELLED: "bad" };

/** One row per number: who comes, how often, and who does not turn up. */
export default function Customers() {
  const { pack, mode, isOwner, readOnly } = useApp();
  useT();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const timer = setTimeout(() => setDebounced(q.trim()), 300); return () => clearTimeout(timer); }, [q]);
  const live = mode === "live";
  const loader = live ? () => engine.customers(pack, debounced) : mode === "demo" ? () => Promise.resolve(sample.customers(pack, debounced)) : null;
  const { data, loading, error, reload } = useData(loader, [pack, mode, debounced]);
  const [open, setOpen] = useState<Customer | null>(null);

  if (!live && mode !== "demo") return <NotLive title={t("Customers")} sub={t("Each number is one customer.")} />;

  const search = (
    <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Search by name or number")}
           aria-label={t("Search customers")} inputMode="search" style={{ maxWidth: 320 }} />
  );

  return (
    <Page title={t("Customers")} sub={t("Who came how often, what they had last time, and how often they did not turn up. Open a row for the full record.")} actions={search}>
      <Panel title={t("Register")} hint={data ? tn("{n} customer", "{n} customers", data.length) + (debounced ? ` · "${debounced}"` : "") : ""}>
        {loading && !data ? <Loading kind="table" />
          : !data ? <Empty>{t("Could not load: {error}", { error: error ?? "" })}<button className="btn btn-ghost btn-sm" onClick={reload}>{t("Try again")}</button></Empty>
          : data.length === 0 ? <Empty><p>{debounced ? t("No customer matches \"{q}\".", { q: debounced }) : t("No customers yet. They appear with the first booking.")}</p></Empty>
          : (
            <Register cards head={<><th>{t("Name")}</th><th>{t("Number")}</th><th className="right">{t("Times visited")}</th><th>{t("Last visited")}</th><th>{t("Most recent service")}</th><th className="right">{t("Did not come")}</th></>}>
              {data.map((c, i) => (
                <tr key={c.phone} {...rowButton(() => setOpen(c), t("Open the record of {name}", { name: c.name || c.phone }))} data-reveal style={{ "--i": Math.min(i, 20) } as CSSProperties}>
                  <td><strong>{c.name || "—"}</strong></td>
                  <td className="mono">{c.phone}</td>
                  <td className="num right">{c.visits}</td>
                  <td>{c.last_visit ? fmtDate(c.last_visit) : "—"}</td>
                  <td>{c.last_service ?? "—"}</td>
                  <td className="num right">{c.no_shows > 0 ? <Chip kind={c.no_shows > 1 ? "bad" : "warn"}>{c.no_shows}</Chip> : "0"}</td>
                </tr>
              ))}
            </Register>
          )}
      </Panel>
      {open && (
        <CustomerDrawer customer={open} pack={pack} live={live} isOwner={isOwner && !readOnly}
                        onClose={() => setOpen(null)} onErased={() => { setOpen(null); reload(); }} />
      )}
    </Page>
  );
}

/** The drawer: the row's own numbers for everyone; for the owner, everything
 *  the engine holds about the number (DPDP right of access) and the right to
 *  erasure. Staff see the phone masked, so the record cannot open for them. */
function CustomerDrawer({ customer: c, pack, live, isOwner, onClose, onErased }:
  { customer: Customer; pack: string; live: boolean; isOwner: boolean; onClose: () => void; onErased: () => void }) {
  const full = c.phone.replace(/\D/g, "").length >= 10;
  const canRecord = isOwner && live && full;
  const rec = useData(canRecord ? () => engine.customerRecord(pack, c.phone) : null, [pack, c.phone, canRecord]);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  useT();
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const erase = async () => {
    setBusy(true); setNote(null);
    try {
      const r = await engine.eraseCustomer(pack, c.phone);
      setNote(t("Erased · {what}", { what: Object.entries(r).map(([k, v]) => `${k} ${v}`).join(", ") }));
      onErased();
    } catch (e) { setNote(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); setConfirm(false); }
  };
  const r = rec.data;
  const hist = useData(() => history(pack, c.phone, live), [pack, c.phone, live]);
  const digits = c.phone.replace(/\D/g, "");
  const reachable = digits.length >= 10;
  const day = today();
  const upcoming = (hist.data?.bookings ?? []).filter((b) => b.date >= day && b.status === "CONFIRMED");
  const past = (hist.data?.bookings ?? []).filter((b) => b.date < day || b.status !== "CONFIRMED").reverse();
  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={t("Record of {name}", { name: c.name || c.phone })}>
        <header>
          <div><h2>{c.name || t("No name")}</h2><p className="muted mono">{c.phone}</p></div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label={t("Close")}><Icon name="x" small /></button>
        </header>
        <div className="body">
          <dl>
            <dt>{t("Visits")}</dt><dd>{c.visits}</dd>
            <dt>{t("Bookings")}</dt><dd>{t("{n} confirmed", { n: c.bookings })}</dd>
            <dt>{t("No-shows")}</dt><dd>{c.no_shows}</dd>
            <dt>{t("Last visit")}</dt><dd>{c.last_visit ? fmtDate(c.last_visit) : "—"}</dd>
            <dt>{t("Last service")}</dt><dd>{c.last_service ?? "—"}</dd>
          </dl>
          <div className="row">
            <a className="btn btn-primary btn-sm" href={reachable ? `tel:+91${digits.slice(-10)}` : undefined} aria-disabled={!reachable}
               title={reachable ? undefined : t("The number is hidden (demo or staff view)")} onClick={(e) => { if (!reachable) e.preventDefault(); }}>
              <Icon name="phone" small />{t("Call them")}</a>
            <a className="btn btn-ghost btn-sm" href={reachable ? `https://wa.me/91${digits.slice(-10)}` : undefined} target="_blank" rel="noopener noreferrer"
               aria-disabled={!reachable} title={reachable ? undefined : t("The number is hidden (demo or staff view)")} onClick={(e) => { if (!reachable) e.preventDefault(); }}>
              {t("WhatsApp them")}</a>
          </div>
          {hist.loading && !hist.data && <p className="muted small">{t("Loading bookings and calls…")}</p>}
          {hist.data && (
            <section className="history">
              <h3>{t("Upcoming bookings")}</h3>
              {upcoming.length ? <div className="list">{upcoming.map((b) => (
                <div key={b.booking_id}><span>{fmtDate(b.date)} {b.time} · {b.service} · {b.staff}</span><Chip>{b.receipt_code}</Chip></div>))}</div>
                : <p className="muted small">{t("None.")}</p>}
              <h3>{t("Past bookings")}</h3>
              {past.length ? <div className="list">{past.slice(0, 8).map((b) => (
                <div key={b.booking_id}><span>{fmtDate(b.date)} {b.time} · {b.service}</span><Chip kind={BK_KIND[b.status]}>{b.status.toLowerCase().replace("_", "-")}</Chip></div>))}</div>
                : <p className="muted small">{t("None.")}</p>}
              <h3>{t("Recent calls")}</h3>
              {hist.data.calls.length ? <div className="list">{hist.data.calls.slice(0, 6).map((x) => (
                <div key={x.call_id}><Link to={`/calls/${encodeURIComponent(x.call_id)}`} onClick={onClose}>{fmtDate(x.started_at)} {fmtTime(x.started_at)}</Link>
                  <Chip>{outcomeLabel(x.outcome)}</Chip></div>))}</div>
                : <p className="muted small">{t("No calls recorded from this number.")}</p>}
            </section>
          )}
          {!isOwner && <p className="muted small">{t("Only the owner can see the full privacy record (calls, WhatsApp, receipts).")}</p>}
          {isOwner && !live && <p className="muted small">{t("This is a sample customer. The privacy record comes from the live engine.")}</p>}
          {isOwner && live && !full && <p className="muted small">{t("A masked number does not open the record; it needs all 10 digits.")}</p>}
          {canRecord && rec.loading && !r && <p className="muted small">{t("Loading the record…")}</p>}
          {rec.error && <p className="muted" role="status">{rec.error}</p>}
          {r && (
            <section>
              <h3>{t("Privacy record (DPDP)")} {r.erased && <Chip kind="bad">{t("erased")}</Chip>}</h3>
              <dl>
                <dt>{t("Bookings")}</dt><dd>{r.bookings.length}</dd>
                <dt>{t("Calls")}</dt><dd>{r.calls.length}</dd>
                <dt>WhatsApp</dt><dd>{t("{n} messages", { n: r.whatsapp_messages })}</dd>
                <dt>{t("Leads")}</dt><dd>{r.leads.length}</dd>
                <dt>{t("Receipts")}</dt><dd>{r.receipts.length}{r.receipts.length ? " " + t("({n} readable)", { n: r.receipts.filter((x) => x.pii_readable).length }) : ""}</dd>
              </dl>
              {r.bookings.length > 0 && (
                <div className="list">
                  {r.bookings.slice(0, 8).map((b) => (
                    <div key={b.booking_id}><span>{fmtDate(b.date)} {b.time} · {b.service}</span><Chip kind={BK_KIND[b.status]}>{b.status.toLowerCase().replace("_", "-")}</Chip></div>
                  ))}
                </div>
              )}
            </section>
          )}
          {canRecord && (
            <div className="danger">
              <p className="muted small">{t("Right to erasure (DPDP Act 2023): the name and number are closed for good. Receipts stay, but can no longer be read.")}</p>
              {confirm
                ? <Confirm text={t("Erase all data for {phone}?", { phone: c.phone })} yes={t("Yes, erase")} busy={busy} onYes={() => void erase()} onNo={() => setConfirm(false)} />
                : <div><button className="btn btn-danger btn-sm" onClick={() => setConfirm(true)} disabled={busy || !!r?.erased}>{t("Erase")}</button></div>}
            </div>
          )}
          {note && <p className="muted" role="status">{note}</p>}
        </div>
      </aside>
    </>
  );
}
