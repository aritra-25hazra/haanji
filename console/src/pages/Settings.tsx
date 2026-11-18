import { useState, type FormEvent } from "react";
import { SettingsPreview } from "../components/Preview";
import { engine } from "../engine";
import { t, useT } from "../i18n";
import { useApp } from "../state";
import { Chip, Confirm, Empty, Icon, Loading, NotLive, Page, Panel, Register, fmtTime, useData } from "../components/Common";
import type { Role, Settings as SettingsShape } from "../types";

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** The owner's page: the pack's knobs, the channels, who may sign in, and the
 *  door out. Staff are told so; the server enforces regardless. */
export default function Settings() {
  const { pack, mode, isOwner, status } = useApp();
  useT();
  if (mode === "demo") return <SettingsPreview pack={pack} />;
  if (mode !== "live") return <NotLive title="Settings" sub="Reminders, deposit, waitlist, digest, users." demo={<p>{t("Settings change only on the live engine, not in the demo.")}</p>} />;
  if (!isOwner) {
    return (
      <Page title="Settings">
        <Empty>
          <p>{t("This page is for the owner only.")}</p>
          <p className="muted small">{t("The owner sets reminders, deposit and users. Ask the owner to change anything.")}</p>
        </Empty>
      </Page>
    );
  }
  const authOn = !!status?.auth?.enabled;
  return (
    <Page title="Settings" sub={t("{pack}: reminders, deposit, waitlist, digest, and who can enter the console.", { pack: pack.replace(/_/g, " ") })}>
      <Connections pack={pack} />
      <SettingsForm key={pack} pack={pack} />
      <GooglePanel pack={pack} />
      <DigestPanel pack={pack} />
      <PrivacyPanel pack={pack} />
      {authOn
        ? <UsersPanel />
        : <Panel title="Users" hint="HAANJI_AUTH off"><Empty><p>{t("The engine runs without sign-in, so everyone is the owner. Users work once HAANJI_AUTH=on.")}</p></Empty></Panel>}
      {authOn && <SessionPanel />}
    </Page>
  );
}

function Connections({ pack }: { pack: string }) {
  const { status } = useApp();
  const g = useData(() => engine.googleStatus(pack), [pack]);
  const wa = status?.whatsapp, ph = status?.phone;
  useT();
  return (
    <Panel title="Connections" hint={t("the channels connected to this engine")}>
      <div className="status-row">
        <Chip kind={wa?.configured ? "ok" : "muted"}><Icon name="phone" small />WhatsApp · {wa?.configured ? `${t("connected")}${wa.number ? ` · ${wa.number}` : ""}` : t("not set")}</Chip>
        <Chip kind={ph?.configured ? "ok" : "muted"}><Icon name="mic" small />Phone line · {ph?.configured ? `${t("connected ")}${ph.number ? ` · ${ph.number}` : ""}` : t("not set")}</Chip>
        <Chip kind={status?.backup?.s3 ? "ok" : "warn"} title={status?.backup?.s3 ? t("Backed up to S3 every night") : t("HAANJI_BACKUP_S3_BUCKET is not set: a redeploy loses bookings and the ledger (docs/operations.md)")}>
          <Icon name="lock" small />Backup · {status?.backup?.s3 ? "S3 nightly" : t("not set; a redeploy loses data")}
        </Chip>
        <Chip kind={g.data?.connected ? "ok" : g.data?.configured ? "warn" : "muted"}>
          <Icon name="calendar" small />Google Calendar · {g.data ? (g.data.connected ? t("connected") : g.data.configured ? t("keys set, not connected") : t("keys not set")) : g.error ? t("unknown") : "…"}
        </Chip>
      </div>
    </Panel>
  );
}

/** GET /api/settings → form → PUT only the keys that changed. */
function SettingsForm({ pack }: { pack: string }) {
  const { readOnly } = useApp();
  const { data, error, reload } = useData(() => engine.settings(pack), [pack]);
  const [draft, setDraft] = useState<Partial<SettingsShape>>({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  useT();
  if (!data) {
    return (
      <Panel title="Booking settings">
        {error ? <Empty>{t("Could not load: {error}", { error })}<button className="btn btn-ghost btn-sm" onClick={reload}>{t("Try again")}</button></Empty> : <Loading />}
      </Panel>
    );
  }
  const cur: SettingsShape = { ...data, ...draft };
  const set = <K extends keyof SettingsShape>(k: K, v: SettingsShape[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const patch = Object.fromEntries(
    (Object.keys(draft) as (keyof SettingsShape)[]).filter((k) => draft[k] !== data[k]).map((k) => [k, draft[k]]),
  ) as Partial<SettingsShape>;
  const dirty = Object.keys(patch).length > 0;
  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!dirty) return;
    setBusy(true); setNote(null);
    try { await engine.saveSettings(pack, patch); setDraft({}); setNote(t("Saved.")); reload(); }
    catch (err) { setNote(msg(err)); }
    finally { setBusy(false); }
  };
  const clampHour = (v: string) => Math.min(23, Math.max(0, Number(v) || 0));
  return (
    <Panel title="Booking settings" hint={dirty ? t("unsaved changes") : t("in sync with the engine")}>
      <form className="body form" onSubmit={(e) => void save(e)}>
        <div className="settings-grid">
          <label className="check"><input type="checkbox" checked={cur.reminders_on} onChange={(e) => set("reminders_on", e.target.checked)} /> {t("Reminders on WhatsApp")}</label>
          <label className="field"><span>{t("Reminder time (IST, 0–23)")}</span>
            <input className="input" type="number" min={0} max={23} value={cur.reminder_hour_ist} onChange={(e) => set("reminder_hour_ist", clampHour(e.target.value))} /></label>
          <label className="check"><input type="checkbox" checked={cur.reminder_day_before} onChange={(e) => set("reminder_day_before", e.target.checked)} /> {t("A day before as well")}</label>
          <label className="field"><span>{t("Deposit ₹ (0 = none)")}</span>
            <input className="input" type="number" min={0} step={50} value={cur.deposit_inr} onChange={(e) => set("deposit_inr", Math.max(0, Number(e.target.value) || 0))} /></label>
          <label className="check"><input type="checkbox" checked={cur.waitlist_on} onChange={(e) => set("waitlist_on", e.target.checked)} /> {t("Waitlist (take a number when the day is full)")}</label>
          <label className="field"><span>{t("Evening digest (IST, 0–23)")}</span>
            <input className="input" type="number" min={0} max={23} value={cur.digest_hour_ist} onChange={(e) => set("digest_hour_ist", clampHour(e.target.value))} /></label>
          <label className="field"><span>WhatsApp script</span>
            <select className="input" value={cur.language_script} onChange={(e) => set("language_script", e.target.value)}>
              <option value="latin">Roman (Hinglish)</option><option value="devanagari">Devanagari</option>
            </select></label>
          <label className="field"><span>{t("Evening summary language")}</span>
            <select className="input" value={cur.owner_language ?? "hi"} onChange={(e) => set("owner_language", e.target.value)}>
              <option value="hi">Hinglish</option><option value="en">English</option>
            </select></label>
          <label className="field"><span>{t("Receptionist salary ₹/month")}</span>
            <input className="input" type="number" min={0} step={500} value={cur.receptionist_monthly_inr ?? 12000}
                   onChange={(e) => set("receptionist_monthly_inr", Math.max(0, Number(e.target.value) || 0))} /></label>
          <label className="field"><span>{t("Calls a receptionist takes in a month")}</span>
            <input className="input" type="number" min={1} step={1} value={cur.receptionist_calls_per_month ?? 1300}
                   onChange={(e) => set("receptionist_calls_per_month", Math.max(1, Number(e.target.value) || 1))} /></label>
        </div>
        <p className="muted small">{t("The \"₹ per call\" comparison comes from these two: salary ÷ calls. The agent's cost comes from the phone, voice and server vendors' rates.")}</p>
        <p className="muted small">{t("With a deposit above 0, every new booking gets a payment link: Razorpay's, or this server's mock link when there are no keys.")}</p>
        <div className="row">
          <button className="btn btn-primary" type="submit" disabled={!dirty || busy || readOnly} title={readOnly ? t("Public demo: settings are read-only") : undefined}>{busy ? t("Saving…") : readOnly ? "Read-only (demo)" : t("Save")}</button>
          {dirty && <button className="btn btn-ghost" type="button" onClick={() => setDraft({})} disabled={busy}>{t("Undo")}</button>}
          {note && <span className="muted" role="status">{note}</span>}
        </div>
      </form>
    </Panel>
  );
}

/** The bookings on the owner's own calendar: a feed URL any app subscribes
 *  to, and a Google Calendar connection when credentials are configured. */
function GooglePanel({ pack }: { pack: string }) {
  // The feed lists customers' names and numbers, so a public demo never hands out its secret URL.
  const { readOnly } = useApp();
  const feed = useData(readOnly ? null : () => engine.feedUrl(pack), [pack, readOnly]);
  const g = useData(() => engine.googleStatus(pack), [pack]);
  const [note, setNote] = useState<string | null>(null);
  useT();
  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); setNote(t("Copied. Paste it into your calendar app under 'subscribe by URL'.")); }
    catch { setNote(text); }
  };
  const connect = async () => {
    try { const r = await engine.googleConnect(pack); window.open(r.url, "_blank", "noopener"); setNote(t("Google opened in a new tab. Give permission, then refresh here.")); }
    catch (e) { setNote(msg(e)); }
  };
  const disconnect = async () => {
    try { await engine.googleDisconnect(pack); g.reload(); setNote(t("Google Calendar removed.")); }
    catch (e) { setNote(msg(e)); }
  };
  const url = feed.data?.url ?? "";
  return (
    <Panel title="Calendar feed & Google" hint={t("every booking on the owner's own calendar")}
           actions={g.data?.configured
             ? (g.data.connected
               ? <button className="btn btn-ghost btn-sm" onClick={() => void disconnect()}>{t("Remove Google")}</button>
               : <button className="btn btn-primary btn-sm" onClick={() => void connect()}>{t("Connect Google Calendar")}</button>)
             : <Chip kind="muted">{t("Google: keys not set")}</Chip>}>
      <div className="body form">
        {feed.data ? (
          <div className="row">
            <label className="field grow"><span>{t("Subscribe URL (\"add by URL\" in Google / Apple / Outlook)")}</span>
              <input className="input mono" readOnly value={url} onFocus={(e) => e.currentTarget.select()} /></label>
            <button className="btn btn-ghost" onClick={() => void copy(url)}>Copy</button>
            <a className="btn btn-ghost" href={feed.data.webcal}>Apple Calendar</a>
          </div>
        ) : <p className="muted">{readOnly ? t("The public demo does not show the feed URL, because it holds customers' names and numbers.")
          : feed.error ? t("Feed URL not found: {error}", { error: feed.error }) : t("Feed URL is coming…")}</p>}
        {g.data?.connected && <p className="muted">{t("Google Calendar is connected")}{g.data.connected_at ? t(" · since {time}", { time: fmtTime(g.data.connected_at) }) : ""}{t(". New bookings become events on their own.")}</p>}
        {note && <p className="muted" role="status">{note}</p>}
      </div>
    </Panel>
  );
}

/** The owner's evening WhatsApp: previewed here, sent by the engine at the
 *  configured hour, or right now from this button. */
function DigestPanel({ pack }: { pack: string }) {
  const { data, error, reload } = useData(() => engine.digest(pack), [pack]);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useT();
  if (!data) return <Panel title={t("Today's digest")}>{error ? <Empty>{t("Digest not found: {error}", { error })}</Empty> : <Loading />}</Panel>;
  const canSend = data.whatsapp_configured && !!data.to;
  const send = async () => {
    setBusy(true); setNote(null);
    try { const r = await engine.sendDigest(pack); setNote(t("Sent · {to}", { to: r.to })); }
    catch (e) { setNote(msg(e)); }
    finally { setBusy(false); reload(); }
  };
  return (
    <Panel title={t("Today's digest")} hint={`${t("WhatsApp to the owner every day at {hour}:00 IST", { hour: data.hour_ist })}${data.to ? ` · ${data.to}` : t(" · number not set")}`}
           actions={<button className="btn btn-primary btn-sm" onClick={() => void send()} disabled={!canSend || busy} title={canSend ? t("Send now") : t("Needs WhatsApp and HAANJI_OWNER_PHONE")}>
             <Icon name="phone" small />{busy ? t("Sending…") : t("Send on WhatsApp now")}</button>}>
      <div className="body">
        <pre className="digest">{data.text}</pre>
        {note && <p className="muted" role="status">{note}</p>}
      </div>
    </Panel>
  );
}

/** Who may sign in: list, add, remove (never yourself). */
const PRIVACY_KIND: Record<string, string> = { export: "Copy downloaded", erase: "Erase my data" };
const PRIVACY_STATUS: Record<string, string> = { DONE: "Done", PENDING: "Waiting for you", ERASED: "Erased", REJECTED: "Refused" };

/** Customers' own requests from the My data page: a copy they took, or an
 *  erasure that waits here for the owner's yes. */
function PrivacyPanel({ pack }: { pack: string }) {
  const { readOnly } = useApp();
  const { data, error, reload } = useData(() => engine.privacyRequests(pack).then((r) => r.requests), [pack]);
  const [asking, setAsking] = useState<{ id: string; approve: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  async function decide(id: string, approve: boolean) {
    setBusy(true); setNote(null);
    try {
      const r = await engine.decidePrivacy(pack, id, approve);
      setNote(r.status === "ERASED" ? t("Erased. The receipts stay sealed, with the name and number unreadable.") : t("Refused. Nothing was erased."));
      reload();
    } catch (e) { setNote((e as Error).message); } finally { setBusy(false); setAsking(null); }
  }
  const rows = data ?? [];
  const open = rows.filter((r) => r.status === "PENDING").length;
  return (
    <Panel title={t("Customers' data requests")} hint={open ? t("{n} waiting for you", { n: open }) : t("from the My data page")}
           actions={<a className="btn btn-ghost btn-sm" href="/engine/my-data" target="_blank" rel="noopener noreferrer">{t("Open My data")} <Icon name="external" small /></a>}>
      {note && <p className="body muted" role="status">{note}</p>}
      {!data ? (error ? <Empty>{t("Could not load: {error}", { error })}</Empty> : <Loading kind="table" />)
        : rows.length === 0 ? <Empty><p>{t("No requests yet. A customer can download or ask to erase their data on the My data page.")}</p></Empty>
        : (
          <Register head={<><th>{t("When")}</th><th>{t("Number")}</th><th>{t("Request")}</th><th>{t("Status")}</th><th /></>}>
            {rows.map((r) => (
              <tr key={r.request_id}>
                <td className="mono">{fmtTime(r.requested_at)}</td>
                <td className="mono">{r.shown}</td>
                <td>{t(PRIVACY_KIND[r.kind] ?? r.kind)}</td>
                <td><Chip kind={r.status === "PENDING" ? "warn" : r.status === "ERASED" ? "ok" : "muted"}>{t(PRIVACY_STATUS[r.status] ?? r.status)}</Chip></td>
                <td className="right">
                  {r.status === "PENDING" && !readOnly && (asking?.id === r.request_id
                    ? <Confirm text={asking.approve ? t("Erase this customer's data for good?") : t("Refuse this request?")} yes={asking.approve ? t("Yes, erase") : t("Yes, refuse")}
                               busy={busy} onYes={() => void decide(r.request_id, asking.approve)} onNo={() => setAsking(null)} />
                    : <span className="row">
                        <button className="btn btn-danger btn-sm" onClick={() => setAsking({ id: r.request_id, approve: true })}>{t("Erase")}</button>
                        <button className="btn btn-ghost btn-sm" onClick={() => setAsking({ id: r.request_id, approve: false })}>{t("Refuse")}</button>
                      </span>)}
                </td>
              </tr>
            ))}
          </Register>
        )}
    </Panel>
  );
}

function UsersPanel() {
  const { readOnly } = useApp();
  const { packs, user: me } = useApp();
  const { data, error, reload } = useData(() => engine.users().then((r) => r.users), []);
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("staff");
  const [sel, setSel] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  useT();
  const digits = phone.replace(/\D/g, "");
  const add = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setNote(null);
    try {
      await engine.addUser({ phone: digits, role, packs: sel.length ? sel : ["*"], name: name.trim() });
      setPhone(""); setName(""); setSel([]); setNote(t("Added · {phone}", { phone: digits })); reload();
    } catch (err) { setNote(msg(err)); }
    finally { setBusy(false); }
  };
  const remove = async (p: string) => {
    setBusy(true); setNote(null);
    try { await engine.removeUser(p); setNote(t("Removed · {phone}", { phone: p })); reload(); }
    catch (err) { setNote(msg(err)); }
    finally { setBusy(false); setRemoving(null); }
  };
  const users = data ?? [];
  return (
    <Panel title="Users" hint={t("owner: everything; staff: calendar, customers, calls")}>
      {error && <p className="muted" style={{ padding: "12px 18px 0" }}>{t("Users did not load: {error}", { error })}</p>}
      <Register head={<><th>{t("Name")}</th><th>Phone</th><th>Role</th><th>Packs</th><th></th></>}>
        {users.map((u) => (
          <tr key={u.phone}>
            <td><strong>{u.name || "—"}</strong></td>
            <td className="mono">{u.phone}</td>
            <td><Chip kind={u.role === "owner" ? "warn" : undefined}>{u.role}</Chip></td>
            <td className="muted">{u.packs.includes("*") ? t("all") : u.packs.join(", ")}</td>
            <td className="right">
              {me?.phone === u.phone
                ? <Chip kind="muted">{t("you")}</Chip>
                : removing === u.phone
                  ? <Confirm text={t("Remove {phone}?", { phone: u.phone })} yes={t("Yes, remove")} busy={busy} onYes={() => void remove(u.phone)} onNo={() => setRemoving(null)} />
                  : <button className="btn btn-ghost btn-sm" onClick={() => setRemoving(u.phone)} disabled={busy}>{t("Remove")}</button>}
            </td>
          </tr>
        ))}
        {data && users.length === 0 && <tr><td colSpan={5} className="muted">{t("No users yet. The first owner comes from HAANJI_OWNER_PHONE.")}</td></tr>}
      </Register>
      <form className="body form" onSubmit={(e) => void add(e)}>
        <div className="row">
          <label className="field"><span>{t("New number (WhatsApp)")}</span>
            <input className="input" inputMode="numeric" autoComplete="off" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" /></label>
          <label className="field grow"><span>{t("Name")}</span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ravi (reception)" /></label>
          <label className="field"><span>Role</span>
            <select className="input" value={role} onChange={(e) => setRole(e.target.value as Role)}><option value="staff">staff</option><option value="owner">owner</option></select></label>
        </div>
        <div className="field"><span>{t("Packs (no tick = all)")}</span>
          <div className="chips">
            {packs.map((p) => {
              const on = sel.includes(p);
              return <label key={p} className="check"><input type="checkbox" checked={on} onChange={() => setSel((s) => (on ? s.filter((x) => x !== p) : [...s, p]))} /> {p}</label>;
            })}
          </div>
        </div>
        <div className="row">
          <button className="btn btn-primary" type="submit" disabled={busy || digits.length < 10 || readOnly}><Icon name="user" small />{t("Add the user")}</button>
          {note && <span className="muted" role="status">{note}</span>}
        </div>
      </form>
    </Panel>
  );
}

function SessionPanel() {
  const { user, signOutEverywhere } = useApp();
  const [busy, setBusy] = useState(false);
  useT();
  return (
    <Panel title="Session" hint={user ? `${user.name || user.phone} · ${user.role}` : ""}>
      <div className="body form">
        <p className="muted">{t("Sign out of every device and browser. All of this number's tokens are revoked on the engine. You will need an OTP to come back in.")}</p>
        <div>
          <button className="btn btn-danger" onClick={() => { setBusy(true); void signOutEverywhere(); }} disabled={busy}>
            <Icon name="lock" small />{busy ? "Sign out…" : "Sign out everywhere"}
          </button>
        </div>
      </div>
    </Panel>
  );
}
