import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { businessName, isTestNumber, outcomeLabel } from "../labels";
import { engine, subscribeLive, enablePush } from "../engine";
import { callbackWhy } from "../callbacks";
import { NEEDS_CALLBACK, sample } from "../sample";
import { useApp } from "../state";
import { t, tn, useLang, useT } from "../i18n";
import AnimatedList from "../components/AnimatedList";
import { Chip, Empty, Icon, Loading, NotLive, OutcomeChip, Page, Panel, Repair, Tile, fmtInr, fmtTime, useData } from "../components/Common";
import { OUTCOMES, type LiveEvent, type LiveSession } from "../types";

const SWATCH: Record<string, string> = {
  BOOKED: "var(--leaf-ink)", RESCHEDULED: "var(--leaf)", FAQ_ANSWERED: "var(--cobalt)", LEAD_CAPTURED: "var(--marigold)",
  HANDED_OFF: "var(--sindoor-ink)", REFUSED: "var(--ink)", ABANDONED: "var(--ink-2)", IN_PROGRESS: "var(--ink-2)",
};

export default function Dashboard() {
  const { pack, mode, status, setSampleView } = useApp();
  useT();
  const live = mode === "live";
  const loader = live ? () => engine.insights(pack) : mode === "demo" ? () => Promise.resolve(sample.insights(pack)) : null;
  const lang = useLang();
  const { data, loading, error, reload } = useData(loader, [pack, mode, lang]);
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(reload, 5000);
    return () => clearInterval(timer);
  }, [live, reload]);

  if (!live && mode !== "demo") return <NotLive title={t("Today")} kind="dashboard" />;
  if (loading && !data) return <Loading kind="dashboard" />;
  if (!data) {
    return (
      <Page title={t("Today")}>
        <div className="empty">{t("Could not load: {error}", { error: error ?? "" })}<button className="btn btn-ghost btn-sm" onClick={reload}>{t("Try again")}</button></div>
      </Page>
    );
  }

  const total = Object.values(data.outcomes).reduce((a, b) => a + b, 0);
  const peak = data.by_hour.reduce((m, h) => (h.calls > m.calls ? h : m), { hour: "—", calls: 0, booked: 0 });
  const quiet = <Empty><p>{t("No calls yet. The graph appears here after the first call.")}</p></Empty>;
  const callbacks = (data.outcomes.LEAD_CAPTURED ?? 0) + (data.outcomes.HANDED_OFF ?? 0);
  const hours = dayHours(data.by_hour);
  const present = OUTCOMES.filter((o) => data.outcomes[o]);

  return (
    <Page title={t("Today")} sub={t("{business}: every call the agent picked up, and what came of it.", { business: businessName(pack) })}
          actions={<>
            {status?.whatsapp?.configured && (isTestNumber(status.whatsapp.number)
              ? <Chip kind="warn" title={t("Meta's sandbox number: only the 5 numbers added to it can talk to it.")}><Icon name="phone" small />{t("Demo WhatsApp number (Meta test)")}</Chip>
              : <Chip kind="ok"><Icon name="phone" small />{t("WhatsApp connected")}{status.whatsapp.number ? ` · ${status.whatsapp.number}` : ""}</Chip>)}
            <Link className="btn btn-ghost btn-sm" to="/calendar"><Icon name="calendar" small />{t("Calendar")}</Link>
          </>}>
      <div className="tiles">
        <Tile index={0} label={t("Calls today")} value={data.calls_today}
              foot={data.calls_yesterday == null ? undefined : data.calls_yesterday === 0 ? t("no calls yesterday")
                    : t("yesterday {n} · {diff}", { n: data.calls_yesterday, diff: `${data.calls_today >= data.calls_yesterday ? "+" : ""}${data.calls_today - data.calls_yesterday}` })} />
        <Tile index={1} label={t("Bookings")} value={data.bookings_confirmed} foot={t("worth {amount}", { amount: fmtInr(data.revenue_booked_inr) })} />
        <Tile index={2} label={t("Needs a callback")} value={callbacks} foot={callbacks ? t("list below") : t("none left")} />
        <Tile index={3} label={t("Missed calls recovered")} value={`${data.missed_calls.recovered}/${data.missed_calls.total}`} foot={t("by WhatsApp")} />
        <Tile index={4} label={t("₹ per call")} value={data.calls_total ? data.cost.ai_per_call_inr : "—"} decimals={2} prefix="₹" mono
              foot={t("receptionist ₹{n} · change in Settings", { n: data.cost.receptionist_per_call_inr.toFixed(2) })}
              hint={t("The agent's cost comes from the vendors' rates; the receptionist's from your salary and calls a month (Settings).")} />
        <Tile index={5} label={t("Misheard, then fixed")} value={data.corrections_total} foot={t("names, services, areas")}
              hint={t("How often the recogniser misheard a word and the agent read it right from your shop's own list (Bhasha Bridge).")} />
      </div>

      {live && data.calls_total === 0 && <FirstSteps whatsapp={!!status?.whatsapp?.configured} onPreview={() => setSampleView(true)} />}
      {data.calls_total > 0 && <Callbacks pack={pack} live={live} />}

      <Panel title={t("Calls through the day")} hint={peak.calls ? tn("busiest {hour}:00 · {n} call", "busiest {hour}:00 · {n} calls", peak.calls, { hour: peak.hour }) : undefined}>
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
              <Bar dataKey="calls" name={t("Calls")} fill="#1B3B8C" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="booked" name={t("Bookings")} fill="#F5B91E" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>}
      </Panel>

      <Panel title={t("How calls ended")} hint={total ? (total === 1 ? t("1 call") : tn("{n} call", "{n} calls", total)) : undefined}>
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

      <Panel title={t("What the engine noticed")} hint={t("made at {time}", { time: fmtTime(data.generated_at) }) + (live ? " · " + t("refreshes every 5 s") : "")}>
        <div className="body">
          {data.insights.length === 0 && <p className="muted">{t("After a few calls, the engine's notes show up here.")}</p>}
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
  useT();
  const steps = [
    { done: false, title: t("Make a test call"), body: t("Talk with the mic in the browser, or type. The booking, the receipt and this dashboard fill in at once."),
      action: <a className="btn btn-primary btn-sm" href="/engine/talk" target="_blank" rel="noopener noreferrer">{t("Open a test call")} <Icon name="external" small /></a> },
    { done: false, title: t("Check services, timings and prices"), body: t("The agent says what the pack says. If something is wrong, fix it in Studio."),
      action: <Link className="btn btn-ghost btn-sm" to="/studio">{t("See it in Studio")}</Link> },
    { done: whatsapp, title: t("Connect your WhatsApp number"), body: whatsapp ? t("Connected. Customers can book by messaging this number.") : t("Connect a Meta WhatsApp Cloud API number to the engine; the guide lists every click."),
      action: whatsapp ? null : <a className="btn btn-ghost btn-sm" href="https://github.com/aritra-25hazra/haanji/blob/main/docs/whatsapp-setup.md" target="_blank" rel="noopener noreferrer">{t("Setup guide")} <Icon name="external" small /></a> },
    { done: false, title: t("Bookings in your phone's calendar"), body: t("One link puts every new booking in Google, Apple or Outlook calendar."),
      action: <Link className="btn btn-ghost btn-sm" to="/settings">{t("Settings")}</Link> },
  ];
  return (
    <Panel title={t("4 steps to get started")} hint={t("{n} of 4 done", { n: steps.filter((x) => x.done).length })}
           actions={<button className="btn btn-ghost btn-sm" onClick={onPreview}>{t("See a sample day")}</button>}>
      <ol className="body first-steps">
        {steps.map((x) => (
          <li key={x.title} className={x.done ? "done" : undefined}>
            <span className="tick" aria-hidden="true">{x.done ? <Icon name="check" small /> : null}</span>
            <div><b>{x.title}</b><p className="muted">{x.body}</p></div>
            {x.action}
            {x.done && <span className="sr-only">{t("done")}</span>}
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
  useT();
  const { data } = useData(live ? () => engine.calls(pack, 500).then((r) => r.conversations) : () => Promise.resolve(sample.calls(pack)), [pack, live]);
  // urgent first (an emergency hand-off), then the newest
  const all = useMemo(() => (data ?? []).filter(NEEDS_CALLBACK).map((c) => ({ c, why: callbackWhy(c) }))
    .sort((a, b) => Number(b.why.urgent) - Number(a.why.urgent) || b.c.started_at.localeCompare(a.c.started_at)), [data]);
  const [shown, setShown] = useState(PAGE);
  const rows = all.slice(0, shown);
  const handoffs = all.filter(({ c }) => c.outcome === "HANDED_OFF").length;
  const urgent = all.filter(({ why }) => why.urgent).length;
  return (
    <Panel title={t("Call these people back")} hint={all.length ? tn("{n} person", "{n} people", all.length) + (handoffs ? " " + t("({n} passed to staff)", { n: handoffs }) : "") + (urgent ? " · " + t("{n} urgent on top", { n: urgent }) : "") + " · " + t("newest first") : t("everyone got an answer")}>
      {all.length === 0
        ? <Empty><p>{t("Callers whose job could not be done on the call show up here. Nobody right now.")}</p></Empty>
        : <ul className="body callbacks">
            {rows.map(({ c, why }) => (
              <li key={c.call_id} className={why.urgent ? "urgent" : undefined}>
                <span className="mono muted">{fmtTime(c.started_at)}</span>
                {c.phone && !/[…X]/.test(c.phone)
                  ? <a className="mono" href={`tel:${c.phone}`}>{c.phone}</a>
                  : <span className="mono">{c.phone ?? t("no number")}</span>}
                <span className="ask"><Chip kind={why.urgent ? "bad" : "muted"}>{why.urgent ? `URGENT · ${why.tag}` : why.tag}</Chip> “{why.ask}”</span>
                <OutcomeChip outcome={c.outcome} />
                <Link to={`/calls/${encodeURIComponent(c.call_id)}`}>{t("Full call")}</Link>
              </li>
            ))}
            {all.length > shown && (
              <li className="more"><button className="btn btn-ghost btn-sm" onClick={() => setShown((n) => n + PAGE)}>{t("Show more ({n} left)", { n: all.length - shown })}</button></li>
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
  useT();
  const refreshSessions = useCallback(() => { engine.liveSessions(pack).then((r) => setSessions(r.sessions)).catch(() => undefined); }, [pack]);
  useEffect(() => {
    refreshSessions();
    const timer = setInterval(refreshSessions, 4000);
    const off = subscribeLive(pack, (e) => {
      if (e.kind === "partial") { setPartial((p) => ({ ...p, [e.sid ?? ""]: e.text ?? "" })); return; }
      if (e.kind === "turn") setPartial((p) => { const n = { ...p }; delete n[e.sid ?? ""]; return n; });
      if (e.kind === "session.ended") onEnded();
      if (e.kind === "session.started" || e.kind === "session.ended" || e.kind === "session.takeover" || e.kind === "session.handback") refreshSessions();
      setEvents((cur) => [e, ...cur].slice(0, 14));
    });
    return () => { off(); clearInterval(timer); };
  }, [pack, onEnded, refreshSessions]);
  const live = Object.entries(partial).filter(([, text]) => text);
  const mine = sessions.find((s) => s.human);
  const send = async () => {
    if (!mine || !reply.trim()) return;
    await engine.humanReply(mine.sid, reply.trim()); setReply("");
  };
  return (
    <Panel title={t("Right now")} hint={events.length ? t("live from the engine, as the call goes") : t("a call shows here as soon as it comes in")}
           actions={<button className="btn btn-ghost btn-sm" onClick={() => enablePush(pack).then(setPushNote).catch((e) => setPushNote(String(e)))} title={t("A phone notification for each new booking")}>{t("Turn on notifications")}</button>}>
      <div className="body feed" aria-live="polite">
        {pushNote && <p className="muted" role="status">{pushNote}</p>}
        {sessions.length > 0 && (
          <div className="live-sessions">
            {sessions.map((s) => (
              <div key={s.sid} className={"ls" + (s.human ? " mine" : "")}>
                <span className="mono">{s.channel.toLowerCase()}{s.phone ? ` · ${s.phone}` : ""} · {t("{n} exchanges", { n: s.turns })}</span>
                <span className="muted">{s.last_caller ? `“${s.last_caller}”` : "—"}</span>
                {s.human
                  ? <button className="btn btn-ghost btn-sm" onClick={() => engine.handback(s.sid).then(refreshSessions)}>{t("Back to the agent")}</button>
                  : <button className="btn btn-primary btn-sm" onClick={() => engine.takeover(s.sid).then(refreshSessions)} title={t("The agent pauses and you answer the caller yourself")}>{t("Answer yourself")}</button>}
              </div>
            ))}
            {mine && (
              <form className="row" onSubmit={(e) => { e.preventDefault(); void send(); }}>
                <input className="input grow" value={reply} onChange={(e) => setReply(e.target.value)} placeholder={t("What to tell the caller… (Enter)")} aria-label={t("Your reply")} />
                <button className="btn btn-primary btn-sm" type="submit" disabled={!reply.trim()}>{t("Send")}</button>
              </form>
            )}
          </div>
        )}
        {live.map(([sid, text]) => <p key={sid} className="ev partial"><i className="dot" />{t("speaking…")} <span className="muted">{text}</span></p>)}
        {events.length === 0 && live.length === 0 && (
          <p className="muted">{t("Try a call:")} <a href="/engine/talk" target="_blank" rel="noopener noreferrer">/talk</a> {t("or the WhatsApp simulator. Each turn shows up here at once.")}</p>
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
  useT();
  return (
          <div className={"ev " + e.kind.replace(".", "-")}>
              <span className="when mono">{fmtTime(e.at)}</span>
              {e.kind === "session.started" && <span>{t("Call started")} · {e.channel?.toLowerCase()}{e.phone ? ` · ${e.phone}` : ""} · <em>{e.greeting}</em></span>}
              {e.kind === "session.takeover" && <span><Chip kind="warn">{t("a person took the call")}</Chip> {e.by}</span>}
              {e.kind === "session.handback" && <span><Chip kind="ok">{t("back with the agent")}</Chip></span>}
              {e.kind === "turn" && e.awaiting_human && <span className="muted"> · {t("needs your reply")}</span>}
              {e.kind === "turn" && (
                <span className="turn">
                  <span className="heard">{e.corrections && e.corrections.length > 0
                    ? e.corrections.map((c, i) => <Repair key={i} c={c} />)
                    : <>“{e.corrected || e.heard}”</>}</span>
                  <span className="said">{e.reply}</span>
                  <span className="chips">
                    {e.tools?.map((tool) => <Chip key={tool} kind={e.speculation_hits?.includes(tool) ? "ok" : undefined} mono>{tool}{e.speculation_hits?.includes(tool) ? " · speculated" : ""}</Chip>)}
                    {Array.isArray(e.receipts) && e.receipts.map((r) => <Chip key={r} kind="warn" mono>RECEIPT {r}</Chip>)}
                    {e.guard && <Chip kind="bad">{e.guard}</Chip>}
                    {typeof e.latency_ms === "number" && <span className="muted mono">{Math.round(e.latency_ms)} ms</span>}
                  </span>
                </span>
              )}
              {e.kind === "session.ended" && <span>{t("Call ended")} · <OutcomeChip outcome={e.outcome ?? null} /> · {e.turns} turns{typeof e.receipts === "number" && e.receipts > 0 ? ` · ${e.receipts} receipt` : ""}</span>}
            </div>
  );
}
