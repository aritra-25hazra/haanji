import { useState, type FormEvent } from "react";
import { engine } from "../engine";
import { useApp } from "../state";
import { Chip, Confirm, Empty, Icon, Loading, NotLive, Page, Panel, Register, fmtTime, useData } from "../components/Common";
import type { Role, Settings as SettingsShape } from "../types";

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** The owner's page: the pack's knobs, the channels, who may sign in, and the
 *  door out. Staff are told so; the server enforces regardless. */
export default function Settings() {
  const { pack, mode, isOwner, status } = useApp();
  if (mode !== "live") return <NotLive title="Settings" sub="Reminders, deposit, waitlist, digest, users." demo={<p>Settings live engine pe hi badalti hain — demo mein nahi.</p>} />;
  if (!isOwner) {
    return (
      <Page title="Settings">
        <Empty>
          <p>Yeh page sirf owner ke liye hai.</p>
          <p className="muted small">Reminders, deposit, users — owner set karta hai. Kuch badalna ho to owner se kaho.</p>
        </Empty>
      </Page>
    );
  }
  const authOn = !!status?.auth?.enabled;
  return (
    <Page title="Settings" sub={`${pack.replace(/_/g, " ")} — reminders, deposit, waitlist, digest, aur kaun console mein aa sakta hai.`}>
      <Connections pack={pack} />
      <SettingsForm key={pack} pack={pack} />
      <GooglePanel pack={pack} />
      <DigestPanel pack={pack} />
      {authOn
        ? <UsersPanel />
        : <Panel title="Users" hint="HAANJI_AUTH off"><Empty><p>Engine auth ke bina chal raha hai — har koi owner hai. Users tab kaam karega jab HAANJI_AUTH=on ho.</p></Empty></Panel>}
      {authOn && <SessionPanel />}
    </Page>
  );
}

function Connections({ pack }: { pack: string }) {
  const { status } = useApp();
  const g = useData(() => engine.googleStatus(pack), [pack]);
  const wa = status?.whatsapp, ph = status?.phone;
  return (
    <Panel title="Connections" hint="jo channel is engine se jude hain">
      <div className="status-row">
        <Chip kind={wa?.configured ? "ok" : "muted"}><Icon name="phone" small />WhatsApp · {wa?.configured ? `juda${wa.number ? ` · ${wa.number}` : ""}` : "set nahi"}</Chip>
        <Chip kind={ph?.configured ? "ok" : "muted"}><Icon name="mic" small />Phone line · {ph?.configured ? `judi${ph.number ? ` · ${ph.number}` : ""}` : "set nahi"}</Chip>
        <Chip kind={status?.backup?.s3 ? "ok" : "warn"} title={status?.backup?.s3 ? "Roz raat S3 par backup" : "HAANJI_BACKUP_S3_BUCKET set nahi: redeploy par bookings aur ledger chale jaate hain (docs/operations.md)"}>
          <Icon name="lock" small />Backup · {status?.backup?.s3 ? "S3 nightly" : "set nahi — redeploy par data jaata hai"}
        </Chip>
        <Chip kind={g.data?.connected ? "ok" : g.data?.configured ? "warn" : "muted"}>
          <Icon name="calendar" small />Google Calendar · {g.data ? (g.data.connected ? "juda" : g.data.configured ? "keys hain, connect nahi" : "keys set nahi") : g.error ? "pata nahi" : "…"}
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
  if (!data) {
    return (
      <Panel title="Booking settings">
        {error ? <Empty>Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty> : <Loading />}
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
    try { await engine.saveSettings(pack, patch); setDraft({}); setNote("Save ho gaya."); reload(); }
    catch (err) { setNote(msg(err)); }
    finally { setBusy(false); }
  };
  const clampHour = (v: string) => Math.min(23, Math.max(0, Number(v) || 0));
  return (
    <Panel title="Booking settings" hint={dirty ? "unsaved changes" : "engine ke saath sync"}>
      <form className="body form" onSubmit={(e) => void save(e)}>
        <div className="settings-grid">
          <label className="check"><input type="checkbox" checked={cur.reminders_on} onChange={(e) => set("reminders_on", e.target.checked)} /> Reminders WhatsApp pe</label>
          <label className="field"><span>Reminder ka time (IST, 0–23)</span>
            <input className="input" type="number" min={0} max={23} value={cur.reminder_hour_ist} onChange={(e) => set("reminder_hour_ist", clampHour(e.target.value))} /></label>
          <label className="check"><input type="checkbox" checked={cur.reminder_day_before} onChange={(e) => set("reminder_day_before", e.target.checked)} /> Ek din pehle bhi</label>
          <label className="field"><span>Deposit ₹ (0 = nahi)</span>
            <input className="input" type="number" min={0} step={50} value={cur.deposit_inr} onChange={(e) => set("deposit_inr", Math.max(0, Number(e.target.value) || 0))} /></label>
          <label className="check"><input type="checkbox" checked={cur.waitlist_on} onChange={(e) => set("waitlist_on", e.target.checked)} /> Waitlist (din full ho to number lo)</label>
          <label className="field"><span>Shaam ka digest (IST, 0–23)</span>
            <input className="input" type="number" min={0} max={23} value={cur.digest_hour_ist} onChange={(e) => set("digest_hour_ist", clampHour(e.target.value))} /></label>
          <label className="field"><span>WhatsApp script</span>
            <select className="input" value={cur.language_script} onChange={(e) => set("language_script", e.target.value)}>
              <option value="latin">Roman (Hinglish)</option><option value="devanagari">Devanagari</option>
            </select></label>
        </div>
        <p className="muted small">Deposit 0 se zyada ho to har nayi booking pe payment link jaata hai — Razorpay, ya keys na hon to is server ka mock link.</p>
        <div className="row">
          <button className="btn btn-primary" type="submit" disabled={!dirty || busy || readOnly} title={readOnly ? "Public demo: settings read-only hain" : undefined}>{busy ? "Save…" : readOnly ? "Read-only (demo)" : "Save karo"}</button>
          {dirty && <button className="btn btn-ghost" type="button" onClick={() => setDraft({})} disabled={busy}>Wapas</button>}
          {note && <span className="muted" role="status">{note}</span>}
        </div>
      </form>
    </Panel>
  );
}

/** The bookings on the owner's own calendar: a feed URL any app subscribes
 *  to, and a Google Calendar connection when credentials are configured. */
function GooglePanel({ pack }: { pack: string }) {
  const feed = useData(() => engine.feedUrl(pack), [pack]);
  const g = useData(() => engine.googleStatus(pack), [pack]);
  const [note, setNote] = useState<string | null>(null);
  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); setNote("Copy ho gaya — apne calendar app mein 'subscribe by URL' mein paste karo."); }
    catch { setNote(text); }
  };
  const connect = async () => {
    try { const r = await engine.googleConnect(pack); window.open(r.url, "_blank", "noopener"); setNote("Google ki tab khuli — permission do, phir yahan refresh karo."); }
    catch (e) { setNote(msg(e)); }
  };
  const disconnect = async () => {
    try { await engine.googleDisconnect(pack); g.reload(); setNote("Google Calendar hata diya."); }
    catch (e) { setNote(msg(e)); }
  };
  const url = feed.data?.url ?? "";
  return (
    <Panel title="Calendar feed & Google" hint="har booking owner ke apne calendar pe"
           actions={g.data?.configured
             ? (g.data.connected
               ? <button className="btn btn-ghost btn-sm" onClick={() => void disconnect()}>Google hatao</button>
               : <button className="btn btn-primary btn-sm" onClick={() => void connect()}>Google Calendar jodo</button>)
             : <Chip kind="muted">Google: keys set nahi</Chip>}>
      <div className="body form">
        {feed.data ? (
          <div className="row">
            <label className="field grow"><span>Subscribe URL (Google / Apple / Outlook — "add by URL")</span>
              <input className="input mono" readOnly value={url} onFocus={(e) => e.currentTarget.select()} /></label>
            <button className="btn btn-ghost" onClick={() => void copy(url)}>Copy</button>
            <a className="btn btn-ghost" href={feed.data.webcal}>Apple Calendar</a>
          </div>
        ) : <p className="muted">{feed.error ? `Feed URL nahi mila: ${feed.error}` : "Feed URL aa raha hai…"}</p>}
        {g.data?.connected && <p className="muted">Google Calendar juda hai{g.data.connected_at ? ` · ${fmtTime(g.data.connected_at)} se` : ""}. Nayi bookings apne aap event banti hain.</p>}
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
  if (!data) return <Panel title="Aaj ka digest">{error ? <Empty>Digest nahi mila: {error}</Empty> : <Loading />}</Panel>;
  const canSend = data.whatsapp_configured && !!data.to;
  const send = async () => {
    setBusy(true); setNote(null);
    try { const r = await engine.sendDigest(pack); setNote(`Bhej diya · ${r.to}`); }
    catch (e) { setNote(msg(e)); }
    finally { setBusy(false); reload(); }
  };
  return (
    <Panel title="Aaj ka digest" hint={`roz ${data.hour_ist}:00 IST pe owner ko WhatsApp${data.to ? ` · ${data.to}` : " · number set nahi"}`}
           actions={<button className="btn btn-primary btn-sm" onClick={() => void send()} disabled={!canSend || busy} title={canSend ? "Abhi bhejo" : "WhatsApp aur HAANJI_OWNER_PHONE chahiye"}>
             <Icon name="phone" small />{busy ? "Bhej raha…" : "Abhi WhatsApp pe bhejo"}</button>}>
      <div className="body">
        <pre className="digest">{data.text}</pre>
        {note && <p className="muted" role="status">{note}</p>}
      </div>
    </Panel>
  );
}

/** Who may sign in: list, add, remove (never yourself). */
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
  const digits = phone.replace(/\D/g, "");
  const add = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setNote(null);
    try {
      await engine.addUser({ phone: digits, role, packs: sel.length ? sel : ["*"], name: name.trim() });
      setPhone(""); setName(""); setSel([]); setNote(`Jod diya · ${digits}`); reload();
    } catch (err) { setNote(msg(err)); }
    finally { setBusy(false); }
  };
  const remove = async (p: string) => {
    setBusy(true); setNote(null);
    try { await engine.removeUser(p); setNote(`Hata diya · ${p}`); reload(); }
    catch (err) { setNote(msg(err)); }
    finally { setBusy(false); setRemoving(null); }
  };
  const users = data ?? [];
  return (
    <Panel title="Users" hint="owner sab kuch; staff calendar, customers, calls">
      {error && <p className="muted" style={{ padding: "12px 18px 0" }}>Users load nahi hue: {error}</p>}
      <Register head={<><th>Naam</th><th>Phone</th><th>Role</th><th>Packs</th><th></th></>}>
        {users.map((u) => (
          <tr key={u.phone}>
            <td><strong>{u.name || "—"}</strong></td>
            <td className="mono">{u.phone}</td>
            <td><Chip kind={u.role === "owner" ? "warn" : undefined}>{u.role}</Chip></td>
            <td className="muted">{u.packs.includes("*") ? "sab" : u.packs.join(", ")}</td>
            <td className="right">
              {me?.phone === u.phone
                ? <Chip kind="muted">aap</Chip>
                : removing === u.phone
                  ? <Confirm text={`${u.phone} ko hatao?`} yes="Haan, hatao" busy={busy} onYes={() => void remove(u.phone)} onNo={() => setRemoving(null)} />
                  : <button className="btn btn-ghost btn-sm" onClick={() => setRemoving(u.phone)} disabled={busy}>Hatao</button>}
            </td>
          </tr>
        ))}
        {data && users.length === 0 && <tr><td colSpan={5} className="muted">Abhi koi user nahi — pehla owner HAANJI_OWNER_PHONE se banta hai.</td></tr>}
      </Register>
      <form className="body form" onSubmit={(e) => void add(e)}>
        <div className="row">
          <label className="field"><span>Naya number (WhatsApp)</span>
            <input className="input" inputMode="numeric" autoComplete="off" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" /></label>
          <label className="field grow"><span>Naam</span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ravi (reception)" /></label>
          <label className="field"><span>Role</span>
            <select className="input" value={role} onChange={(e) => setRole(e.target.value as Role)}><option value="staff">staff</option><option value="owner">owner</option></select></label>
        </div>
        <div className="field"><span>Packs (koi tick nahi = sab)</span>
          <div className="chips">
            {packs.map((p) => {
              const on = sel.includes(p);
              return <label key={p} className="check"><input type="checkbox" checked={on} onChange={() => setSel((s) => (on ? s.filter((x) => x !== p) : [...s, p]))} /> {p}</label>;
            })}
          </div>
        </div>
        <div className="row">
          <button className="btn btn-primary" type="submit" disabled={busy || digits.length < 10 || readOnly}><Icon name="user" small />User jodo</button>
          {note && <span className="muted" role="status">{note}</span>}
        </div>
      </form>
    </Panel>
  );
}

function SessionPanel() {
  const { user, signOutEverywhere } = useApp();
  const [busy, setBusy] = useState(false);
  return (
    <Panel title="Session" hint={user ? `${user.name || user.phone} · ${user.role}` : ""}>
      <div className="body form">
        <p className="muted">Har device aur browser se sign out — is number ke saare tokens engine pe revoke ho jaate hain. Dobara OTP se andar aana hoga.</p>
        <div>
          <button className="btn btn-danger" onClick={() => { setBusy(true); void signOutEverywhere(); }} disabled={busy}>
            <Icon name="lock" small />{busy ? "Sign out…" : "Sign out everywhere"}
          </button>
        </div>
      </div>
    </Panel>
  );
}
