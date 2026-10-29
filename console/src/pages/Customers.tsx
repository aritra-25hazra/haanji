import { useEffect, useState, type CSSProperties } from "react";
import { engine } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Chip, Confirm, Empty, Icon, Loading, NotLive, Page, Panel, Register, fmtDate, rowButton, useData, type ChipKind } from "../components/Common";
import type { Customer } from "../types";

const BK_KIND: Record<string, ChipKind | undefined> = { CONFIRMED: undefined, COMPLETED: "ok", NO_SHOW: "warn", CANCELLED: "bad" };

/** One row per number: who comes, how often, and who does not turn up. */
export default function Customers() {
  const { pack, mode, isOwner, readOnly } = useApp();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  const live = mode === "live";
  const loader = live ? () => engine.customers(pack, debounced) : mode === "demo" ? () => Promise.resolve(sample.customers(debounced)) : null;
  const { data, loading, error, reload } = useData(loader, [pack, mode, debounced]);
  const [open, setOpen] = useState<Customer | null>(null);

  if (!live && mode !== "demo") return <NotLive title="Customers" sub="Har number ek customer." />;

  const search = (
    <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Naam ya number ke aakhri digits"
           aria-label="Customer khojo" inputMode="search" style={{ maxWidth: 320 }} />
  );

  return (
    <Page title="Customers" sub="Kaun kitni baar aaya, aakhri baar kya karaya, aur kitni baar nahi aaya. Row kholo to poora record." actions={search}>
      <Panel title="Register" hint={data ? `${data.length} customers${debounced ? ` · "${debounced}"` : ""}` : ""}>
        {loading && !data ? <Loading />
          : !data ? <Empty>Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty>
          : data.length === 0 ? <Empty><p>{debounced ? `"${debounced}" se koi customer nahi mila.` : "Abhi koi customer nahi — pehli booking ke saath aayega."}</p></Empty>
          : (
            <Register head={<><th>Naam</th><th>Phone</th><th className="right">Visits</th><th>Last visit</th><th>Last service</th><th className="right">No-shows</th></>}>
              {data.map((c, i) => (
                <tr key={c.phone} {...rowButton(() => setOpen(c), `${c.name || c.phone} ka record kholo`)} data-reveal style={{ "--i": Math.min(i, 20) } as CSSProperties}>
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
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const erase = async () => {
    setBusy(true); setNote(null);
    try {
      const r = await engine.eraseCustomer(pack, c.phone);
      setNote(`Mita diya · ${Object.entries(r).map(([k, v]) => `${k} ${v}`).join(", ")}`);
      onErased();
    } catch (e) { setNote(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); setConfirm(false); }
  };
  const r = rec.data;
  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`${c.name || c.phone} ka record`}>
        <header>
          <div><h2>{c.name || "Naam nahi"}</h2><p className="muted mono">{c.phone}</p></div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Band karo"><Icon name="x" small /></button>
        </header>
        <div className="body">
          <dl>
            <dt>Visits</dt><dd>{c.visits}</dd>
            <dt>Bookings</dt><dd>{c.bookings} confirmed</dd>
            <dt>No-shows</dt><dd>{c.no_shows}</dd>
            <dt>Last visit</dt><dd>{c.last_visit ? fmtDate(c.last_visit) : "—"}</dd>
            <dt>Last service</dt><dd>{c.last_service ?? "—"}</dd>
          </dl>
          {!isOwner && <p className="muted small">Poora privacy record (calls, WhatsApp, receipts) sirf owner dekh sakta hai.</p>}
          {isOwner && !live && <p className="muted small">Sample customer — privacy record live engine se aata hai.</p>}
          {isOwner && live && !full && <p className="muted small">Masked number pe record nahi khulta — poore 10 digits chahiye.</p>}
          {canRecord && rec.loading && !r && <p className="muted small">Record aa raha hai…</p>}
          {rec.error && <p className="muted" role="status">{rec.error}</p>}
          {r && (
            <section>
              <h3>Privacy record {r.erased && <Chip kind="bad">mitaya hua</Chip>}</h3>
              <dl>
                <dt>Bookings</dt><dd>{r.bookings.length}</dd>
                <dt>Calls</dt><dd>{r.calls.length}</dd>
                <dt>WhatsApp</dt><dd>{r.whatsapp_messages} messages</dd>
                <dt>Leads</dt><dd>{r.leads.length}</dd>
                <dt>Receipts</dt><dd>{r.receipts.length}{r.receipts.length ? ` (${r.receipts.filter((x) => x.pii_readable).length} readable)` : ""}</dd>
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
              <p className="muted small">Right to erasure (DPDP Act 2023): naam-number hamesha ke liye band. Receipts rahengi, par padhi nahi ja sakengi.</p>
              {confirm
                ? <Confirm text={`${c.phone} ka sab data mita dein?`} yes="Haan, mita do" busy={busy} onYes={() => void erase()} onNo={() => setConfirm(false)} />
                : <div><button className="btn btn-danger btn-sm" onClick={() => setConfirm(true)} disabled={busy || !!r?.erased}>Mita do</button></div>}
            </div>
          )}
          {note && <p className="muted" role="status">{note}</p>}
        </div>
      </aside>
    </>
  );
}
