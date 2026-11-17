import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { businessName, isTestNumber, outcomeLabel } from "../labels";
import { engine, subscribeLive, enablePush } from "../engine";
import { callbackWhy } from "../callbacks";
import { NEEDS_CALLBACK, sample } from "../sample";
import { useApp } from "../state";
import AnimatedList from "../components/AnimatedList";
import { Chip, Empty, Icon, Loading, NotLive, OutcomeChip, Page, Panel, Repair, Tile, fmtInr, fmtTime, useData } from "../components/Common";
import { OUTCOMES, type LiveEvent, type LiveSession } from "../types";

const SWATCH: Record<string, string> = {
  BOOKED: "var(--leaf-ink)", RESCHEDULED: "var(--leaf)", FAQ_ANSWERED: "var(--cobalt)", LEAD_CAPTURED: "var(--marigold)",
  HANDED_OFF: "var(--sindoor-ink)", REFUSED: "var(--ink)", ABANDONED: "var(--ink-2)", IN_PROGRESS: "var(--ink-2)",
};

export default function Dashboard() {
  const { pack, mode, status, setSampleView } = useApp();
  const live = mode === "live";
  const loader = live ? () => engine.insights(pack) : mode === "demo" ? () => Promise.resolve(sample.insights(pack)) : null;
  const { data, loading, error, reload } = useData(loader, [pack, mode]);
  useEffect(() => {
    if (!live) return;
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
  }, [live, reload]);

  if (!live && mode !== "demo") return <NotLive title="Aaj" />;
  if (loading && !data) return <Loading kind="dashboard" />;
  if (!data) {
    return (
      <Page title="Aaj">
        <div className="empty">Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></div>
      </Page>
    );
  }

  const total = Object.values(data.outcomes).reduce((a, b) => a + b, 0);
  const peak = data.by_hour.reduce((m, h) => (h.calls > m.calls ? h : m), { hour: "—", calls: 0, booked: 0 });
  const quiet = <Empty><p>Abhi koi call nahi aayi. Pehli call ke baad yahan graph banega.</p></Empty>;
  const callbacks = (data.outcomes.LEAD_CAPTURED ?? 0) + (data.outcomes.HANDED_OFF ?? 0);
  const hours = dayHours(data.by_hour);
  const present = OUTCOMES.filter((o) => data.outcomes[o]);

  return (
    <Page title="Aaj" sub={`${businessName(pack)}: har call jo agent ne uthayi, aur usse kya nikla.`}
          actions={<>
            {status?.whatsapp?.configured && (isTestNumber(status.whatsapp.number)
              ? <Chip kind="warn" title="Meta ka sandbox number: sirf jode gaye 5 numbers isse baat kar sakte hain."><Icon name="phone" small />Test WhatsApp (Meta sandbox){status.whatsapp.number ? ` · ${status.whatsapp.number}` : ""}</Chip>
              : <Chip kind="ok"><Icon name="phone" small />WhatsApp juda hai{status.whatsapp.number ? ` · ${status.whatsapp.number}` : ""}</Chip>)}
            <Link className="btn btn-ghost btn-sm" to="/calendar"><Icon name="calendar" small />Calendar</Link>
          </>}>
      <div className="tiles">
        <Tile index={0} label="Calls aaj" value={data.calls_today}
              foot={data.calls_yesterday == null ? undefined : data.calls_yesterday === 0 ? "kal koi call nahi"
                    : `kal ${data.calls_yesterday} · ${data.calls_today >= data.calls_yesterday ? "+" : ""}${data.calls_today - data.calls_yesterday}`} />
        <Tile index={1} label="Bookings" value={data.bookings_confirmed} foot={`${fmtInr(data.revenue_booked_inr)} ki`} />
        <Tile index={2} label="Callback chahiye" value={callbacks} foot={callbacks ? "neeche list hai" : "koi baaki nahi"} />
        <Tile index={3} label="Missed calls wapas" value={`${data.missed_calls.recovered}/${data.missed_calls.total}`} foot="WhatsApp se" />
        <Tile index={4} label="₹ per call" value={data.calls_total ? data.cost.ai_per_call_inr : "—"} decimals={2} prefix="₹" mono
              foot={`receptionist ₹${data.cost.receptionist_per_call_inr.toFixed(2)} · Settings mein badlo`}
              hint="Agent ka kharcha vendors ke rate se; receptionist ka aapki tankhwah aur mahine ki calls se (Settings)." />
        <Tile index={5} label="Galat suna, theek kiya" value={data.corrections_total} foot="naam, services, ilaake"
              hint="Recogniser ne jo shabd galat suna aur agent ne aapki dukaan ki list se sahi padha, uski ginti (Bhasha Bridge)." />
      </div>

      {live && data.calls_total === 0 && <FirstSteps whatsapp={!!status?.whatsapp?.configured} onPreview={() => setSampleView(true)} />}
      {data.calls_total > 0 && <Callbacks pack={pack} live={live} />}

      <Panel title="Din bhar ki calls" hint={peak.calls ? `sabse busy ${peak.hour}:00 · ${peak.calls} calls` : undefined}>
        {peak.calls === 0 ? quiet : <div className="body" style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={hours} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid stroke="rgba(27,59,140,.14)" vertical={false} />
              <XAxis dataKey="hour" tickLine={false} axisLine={{ stroke: "rgba(27,59,140,.3)" }} tick={{ fontSize: 12, fill: "rgba(20,33,61,.68)" }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "rgba(20,33,61,.68)" }} allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(27,59,140,.06)" }} contentStyle={{ borderRadius: 8, border: "1px solid rgba(27,59,140,.14)", fontSize: 13 }} />
              {/* recharts reads attributes, not CSS variables: these are the system's cobalt and marigold. */}
              {/* No grow-in: the panel refreshes every 5 s and would replay it each time. */}
              <Legend verticalAlign="top" align="right" height={28} iconType="square" wrapperStyle={{ fontSize: 13 }} />
              <Bar dataKey="calls" name="Calls" fill="#1B3B8C" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="booked" name="Bookings" fill="#F5B91E" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>}
      </Panel>

      <Panel title="Calls kaise khatam huin" hint={total ? `${total} ${total === 1 ? "call" : "calls"}` : undefined}>
        {total === 0 ? quiet : <div className="body">
          <div className="obar" role="img" aria-label={present.map((o) => `${o.toLowerCase().replace(/_/g, " ")} ${data.outcomes[o]}`).join(", ")}>
            {present.map((o) => <i key={o} className={o} style={{ width: `${((data.outcomes[o] ?? 0) / total) * 100}%` }} />)}
          </div>
          <div className="legend">
            {present.map((o) => (
              <span key={o}><i style={{ background: SWATCH[o] }} />{outcomeLabel(o)} · {data.outcomes[o]}</span>
            ))}
          </div>
        </div>}
      </Panel>

      {live && <LivePanel key={pack} pack={pack} onEnded={reload} />}

      <Panel title="Engine ne kya dekha" hint={`${fmtTime(data.generated_at)} pe bana${live ? " · har 5 s refresh" : ""}`}>
        <div className="body">
          {data.insights.length === 0 && <p className="muted">Kuch calls hone do, phir yahan engine ki baatein dikhengi.</p>}
          {data.insights.map((line, i) => <p key={i} data-reveal style={{ "--i": i, margin: "6px 0" } as CSSProperties}>• {line}</p>)}
        </div>
      </Panel>
    </Page>
  );
}


/** The working day on the x-axis (8:00 to 21:00, wider if a call came
 *  earlier or later), so one busy hour reads as a bar in a day rather than a
 *  lone column. */
function dayHours(rows: { hour: string; calls: number; booked: number }[]) {
  const seen = new Map(rows.map((r) => [Number(r.hour), r]));
  const lo = Math.min(8, ...seen.keys()), hi = Math.max(21, ...seen.keys());
  const out = [];
  for (let h = lo; h <= hi; h++) out.push(seen.get(h) ?? { hour: String(h).padStart(2, "0"), calls: 0, booked: 0 });
  return out;
}

/** What a shop does before its first call, each step marked done from what
 *  the engine reports. Disappears once a call has come in. */
function FirstSteps({ whatsapp, onPreview }: { whatsapp: boolean; onPreview: () => void }) {
  const steps = [
    { done: false, title: "Ek test call karo", body: "Browser mein mic se ya type karke baat karo. Booking, receipt aur ye dashboard turant bharenge.",
      action: <a className="btn btn-primary btn-sm" href="/engine/talk" target="_blank" rel="noopener noreferrer">Test call kholo <Icon name="external" small /></a> },
    { done: false, title: "Services, timing aur daam check karo", body: "Agent wahi bolta hai jo pack mein likha hai. Galat ho to Studio mein theek karo.",
      action: <Link className="btn btn-ghost btn-sm" to="/studio">Studio mein dekho</Link> },
    { done: whatsapp, title: "Apna WhatsApp number jodo", body: whatsapp ? "Juda hai. Customers is number pe message karke booking kar sakte hain." : "Meta ka WhatsApp Cloud API number engine se jodo; guide mein har click likha hai.",
      action: whatsapp ? null : <a className="btn btn-ghost btn-sm" href="https://github.com/aritra-25hazra/haanji/blob/main/docs/whatsapp-setup.md" target="_blank" rel="noopener noreferrer">Setup guide <Icon name="external" small /></a> },
    { done: false, title: "Bookings apne phone ke calendar mein", body: "Ek link se har nayi booking Google, Apple ya Outlook calendar mein aa jaati hai.",
      action: <Link className="btn btn-ghost btn-sm" to="/settings">Settings</Link> },
  ];
  return (
    <Panel title="Shuru karne ke 4 kadam" hint={`${steps.filter((x) => x.done).length} of 4 ho gaye`}
           actions={<button className="btn btn-ghost btn-sm" onClick={onPreview}>Sample din dekho</button>}>
      <ol className="body first-steps">
        {steps.map((x) => (
          <li key={x.title} className={x.done ? "done" : undefined}>
            <span className="tick" aria-hidden="true">{x.done ? <Icon name="check" small /> : null}</span>
            <div><b>{x.title}</b><p className="muted">{x.body}</p></div>
            {x.action}
            {x.done && <span className="sr-only">ho gaya</span>}
          </li>
        ))}
      </ol>
    </Panel>
  );
}

const PAGE = 10;

/** Callers who left a number or asked for a person: the shop's to-do list.
 *  The same rule as the "Callback chahiye" tile (NEEDS_CALLBACK), over the
 *  same calls the insights count (the engine's last 500), every one listed. */
function Callbacks({ pack, live }: { pack: string; live: boolean }) {
  const { data } = useData(live ? () => engine.calls(pack, 500).then((r) => r.conversations) : () => Promise.resolve(sample.calls(pack)), [pack, live]);
  // urgent first (an emergency hand-off), then the newest
  const all = useMemo(() => (data ?? []).filter(NEEDS_CALLBACK).map((c) => ({ c, why: callbackWhy(c) }))
    .sort((a, b) => Number(b.why.urgent) - Number(a.why.urgent) || b.c.started_at.localeCompare(a.c.started_at)), [data]);
  const [shown, setShown] = useState(PAGE);
  const rows = all.slice(0, shown);
  const handoffs = all.filter(({ c }) => c.outcome === "HANDED_OFF").length;
  const urgent = all.filter(({ why }) => why.urgent).length;
  return (
    <Panel title="Inhe wapas call karo" hint={all.length ? `${all.length} log${handoffs ? ` (${handoffs} insaan ko diye)` : ""}${urgent ? ` · ${urgent} urgent upar` : ""} · naye pehle` : "sab ko jawab mil gaya"}>
      {all.length === 0
        ? <Empty><p>Jinka kaam call pe nahi ho paaya, wo yahan aate hain. Abhi koi nahi.</p></Empty>
        : <ul className="body callbacks">
            {rows.map(({ c, why }) => (
              <li key={c.call_id} className={why.urgent ? "urgent" : undefined}>
                <span className="mono muted">{fmtTime(c.started_at)}</span>
                {c.phone && !/[…X]/.test(c.phone)
                  ? <a className="mono" href={`tel:${c.phone}`}>{c.phone}</a>
                  : <span className="mono">{c.phone ?? "number nahi"}</span>}
                <span className="ask"><Chip kind={why.urgent ? "bad" : "muted"}>{why.urgent ? `URGENT · ${why.tag}` : why.tag}</Chip> “{why.ask}”</span>
                <OutcomeChip outcome={c.outcome} />
                <Link to={`/calls/${encodeURIComponent(c.call_id)}`}>Poori baat</Link>
              </li>
            ))}
            {all.length > shown && (
              <li className="more"><button className="btn btn-ghost btn-sm" onClick={() => setShown((n) => n + PAGE)}>Aur dikhao ({all.length - shown} baaki)</button></li>
            )}
          </ul>}
    </Panel>
  );
}


/** Calls as they happen: the engine's event stream, newest at the top. The
 *  parent keys this by pack, so a pack switch starts a clean feed. */
function LivePanel({ pack, onEnded }: { pack: string; onEnded: () => void }) {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [partial, setPartial] = useState<Record<string, string>>({});
  const [sessions, setSessions] = useState<LiveSession[]>([]);
  const [reply, setReply] = useState("");
  const [pushNote, setPushNote] = useState<string | null>(null);
  const refreshSessions = useCallback(() => { engine.liveSessions(pack).then((r) => setSessions(r.sessions)).catch(() => undefined); }, [pack]);
  useEffect(() => {
    refreshSessions();
    const t = setInterval(refreshSessions, 4000);
    const off = subscribeLive(pack, (e) => {
      if (e.kind === "partial") { setPartial((p) => ({ ...p, [e.sid ?? ""]: e.text ?? "" })); return; }
      if (e.kind === "turn") setPartial((p) => { const n = { ...p }; delete n[e.sid ?? ""]; return n; });
      if (e.kind === "session.ended") onEnded();
      if (e.kind === "session.started" || e.kind === "session.ended" || e.kind === "session.takeover" || e.kind === "session.handback") refreshSessions();
      setEvents((cur) => [e, ...cur].slice(0, 14));
    });
    return () => { off(); clearInterval(t); };
  }, [pack, onEnded, refreshSessions]);
  const live = Object.entries(partial).filter(([, t]) => t);
  const mine = sessions.find((s) => s.human);
  const send = async () => {
    if (!mine || !reply.trim()) return;
    await engine.humanReply(mine.sid, reply.trim()); setReply("");
  };
  return (
    <Panel title="Abhi" hint={events.length ? "engine se live, jaise-jaise call chalti hai" : "koi call aate hi yahan dikhegi"}
           actions={<button className="btn btn-ghost btn-sm" onClick={() => enablePush(pack).then(setPushNote).catch((e) => setPushNote(String(e)))} title="Nayi booking pe phone pe notification">Notifications on</button>}>
      <div className="body feed" aria-live="polite">
        {pushNote && <p className="muted" role="status">{pushNote}</p>}
        {sessions.length > 0 && (
          <div className="live-sessions">
            {sessions.map((s) => (
              <div key={s.sid} className={"ls" + (s.human ? " mine" : "")}>
                <span className="mono">{s.channel.toLowerCase()}{s.phone ? ` · ${s.phone}` : ""} · {s.turns} baar baat</span>
                <span className="muted">{s.last_caller ? `“${s.last_caller}”` : "—"}</span>
                {s.human
                  ? <button className="btn btn-ghost btn-sm" onClick={() => engine.handback(s.sid).then(refreshSessions)}>Wapas agent ko</button>
                  : <button className="btn btn-primary btn-sm" onClick={() => engine.takeover(s.sid).then(refreshSessions)} title="Agent rukega, caller ko aap khud jawab doge">Khud jawab do</button>}
              </div>
            ))}
            {mine && (
              <form className="row" onSubmit={(e) => { e.preventDefault(); void send(); }}>
                <input className="input grow" value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Caller ko kya bolna hai… (Enter)" aria-label="Human reply" />
                <button className="btn btn-primary btn-sm" type="submit" disabled={!reply.trim()}>Bolo</button>
              </form>
            )}
          </div>
        )}
        {live.map(([sid, t]) => <p key={sid} className="ev partial"><i className="dot" />bol rahe hain… <span className="muted">{t}</span></p>)}
        {events.length === 0 && live.length === 0 && (
          <p className="muted">Ek call karke dekho: <a href="/engine/talk" target="_blank" rel="noopener noreferrer">/talk</a> ya WhatsApp simulator se. Har turn yahan turant aayega.</p>
        )}
        {events.length > 0 && (
          // Slides each new event in at the top; a plain list to assistive tech (the panel is the live region).
          <AnimatedList semantics="list" className="feed-list" items={events.map((e) => ({ id: e.seq, title: e.kind }))}
                        renderItem={(_, i) => { const e = events[i]; return e ? <EventRow e={e} /> : null; }}
                        animation="slide" animateOnce stagger={0} frame={false} showGradients={false} enableArrowNavigation={false}
                        theme="light" gap={6} radius={10} maxHeight={420} displayScrollbar style={FEED_SKIN} />
        )}
      </div>
    </Panel>
  );
}

// AnimatedList's light theme, repainted in the Signboard register.
const FEED_SKIN = {
  "--al-tile": "var(--paper)", "--al-tile-shadow": "none", "--al-tile-edge": "var(--rule)", "--al-ink": "var(--ink)",
  "--al-muted": "var(--ink-2)", "--al-hover": "none", "--al-press": "none", "--al-active": "none", "--al-ring": "transparent",
} as CSSProperties;

function EventRow({ e }: { e: LiveEvent }) {
  return (
          <div className={"ev " + e.kind.replace(".", "-")}>
              <span className="when mono">{fmtTime(e.at)}</span>
              {e.kind === "session.started" && <span>Call shuru · {e.channel?.toLowerCase()}{e.phone ? ` · ${e.phone}` : ""} · <em>{e.greeting}</em></span>}
              {e.kind === "session.takeover" && <span><Chip kind="warn">insaan ne call li</Chip> {e.by}</span>}
              {e.kind === "session.handback" && <span><Chip kind="ok">wapas agent ke paas</Chip></span>}
              {e.kind === "turn" && e.awaiting_human && <span className="muted"> · aapka jawab chahiye</span>}
              {e.kind === "turn" && (
                <span className="turn">
                  <span className="heard">{e.corrections && e.corrections.length > 0
                    ? e.corrections.map((c, i) => <Repair key={i} c={c} />)
                    : <>“{e.corrected || e.heard}”</>}</span>
                  <span className="said">{e.reply}</span>
                  <span className="chips">
                    {e.tools?.map((t) => <Chip key={t} kind={e.speculation_hits?.includes(t) ? "ok" : undefined} mono>{t}{e.speculation_hits?.includes(t) ? " · speculated" : ""}</Chip>)}
                    {Array.isArray(e.receipts) && e.receipts.map((r) => <Chip key={r} kind="warn" mono>RECEIPT {r}</Chip>)}
                    {e.guard && <Chip kind="bad">{e.guard}</Chip>}
                    {typeof e.latency_ms === "number" && <span className="muted mono">{Math.round(e.latency_ms)} ms</span>}
                  </span>
                </span>
              )}
              {e.kind === "session.ended" && <span>Call khatam · <OutcomeChip outcome={e.outcome ?? null} /> · {e.turns} turns{typeof e.receipts === "number" && e.receipts > 0 ? ` · ${e.receipts} receipt` : ""}</span>}
            </div>
  );
}
