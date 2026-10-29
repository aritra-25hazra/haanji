import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { engine, subscribeLive, enablePush } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Chip, Icon, Loading, NotLive, OutcomeChip, Page, Panel, Repair, Tile, fmtInr, fmtTime, useData } from "../components/Common";
import { OUTCOMES, type LiveEvent, type LiveSession } from "../types";

const SWATCH: Record<string, string> = {
  BOOKED: "var(--leaf-ink)", RESCHEDULED: "var(--leaf)", FAQ_ANSWERED: "var(--cobalt)", LEAD_CAPTURED: "var(--marigold)",
  HANDED_OFF: "var(--sindoor-ink)", REFUSED: "var(--ink)", ABANDONED: "var(--ink-2)", IN_PROGRESS: "var(--ink-2)",
};

export default function Dashboard() {
  const { pack, mode, status } = useApp();
  const live = mode === "live";
  const loader = live ? () => engine.insights(pack) : mode === "demo" ? () => Promise.resolve(sample.insights()) : null;
  const { data, loading, error, reload } = useData(loader, [pack, mode]);
  useEffect(() => {
    if (!live) return;
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
  }, [live, reload]);

  if (!live && mode !== "demo") return <NotLive title="Aaj" />;
  if (loading && !data) return <Loading />;
  if (!data) {
    return (
      <Page title="Aaj">
        <div className="empty">Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></div>
      </Page>
    );
  }

  const total = Object.values(data.outcomes).reduce((a, b) => a + b, 0) || 1;
  const peak = data.by_hour.reduce((m, h) => (h.calls > m.calls ? h : m), { hour: "—", calls: 0, booked: 0 });
  const present = OUTCOMES.filter((o) => data.outcomes[o]);

  return (
    <Page title="Aaj" sub={`${pack.replace(/_/g, " ")} — har call jo agent ne uthayi, aur usse kya nikla.`}
          actions={<>
            {status?.whatsapp?.configured && <Chip kind="ok"><Icon name="phone" small />Asli WhatsApp juda hai{status.whatsapp.number ? ` · ${status.whatsapp.number}` : ""}</Chip>}
            <Link className="btn btn-ghost btn-sm" to="/calendar"><Icon name="calendar" small />Calendar</Link>
          </>}>
      <div className="tiles">
        <Tile index={0} label="Calls aaj" value={data.calls_today} foot={`${data.calls_total} kul`} />
        <Tile index={1} label="Bookings" value={data.bookings_confirmed} foot={`${fmtInr(data.revenue_booked_inr)} ki`} />
        <Tile index={2} label="Missed calls wapas" value={`${data.missed_calls.recovered}/${data.missed_calls.total}`} foot="WhatsApp se" />
        <Tile index={3} label="₹ per call" value={data.cost.ai_per_call_inr} decimals={2} prefix="₹" mono foot={`receptionist ₹${data.cost.receptionist_per_call_inr.toFixed(2)}`} />
        <Tile index={4} label="Shabd sudhaare" value={data.corrections_total} foot="Bhasha Bridge" />
        <Tile index={5} label="Speculation hits" value={Math.round(data.speculation.hit_rate * 100)} suffix="%" foot={`${data.speculation.hits} of ${data.speculation.started} tool calls`} />
      </div>

      <Panel title="Din bhar ki calls" hint={`peak ${peak.hour}:00 — ${peak.calls} calls · booked marigold mein`}>
        <div className="body" style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.by_hour} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid stroke="rgba(27,59,140,.14)" vertical={false} />
              <XAxis dataKey="hour" tickLine={false} axisLine={{ stroke: "rgba(27,59,140,.3)" }} tick={{ fontSize: 12, fill: "rgba(20,33,61,.68)" }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "rgba(20,33,61,.68)" }} allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(27,59,140,.06)" }} contentStyle={{ borderRadius: 8, border: "1px solid rgba(27,59,140,.14)", fontSize: 13 }} />
              {/* recharts reads attributes, not CSS variables: these are the system's cobalt and marigold. */}
              <Bar dataKey="calls" name="calls" fill="#1B3B8C" radius={[3, 3, 0, 0]} />
              <Bar dataKey="booked" name="booked" fill="#F5B91E" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <Panel title="Calls kaise khatam huin" hint={`${total} calls`}>
        <div className="body">
          <div className="obar" role="img" aria-label={present.map((o) => `${o.toLowerCase().replace(/_/g, " ")} ${data.outcomes[o]}`).join(", ")}>
            {present.map((o) => <i key={o} className={o} style={{ width: `${((data.outcomes[o] ?? 0) / total) * 100}%` }} />)}
          </div>
          <div className="legend">
            {present.map((o) => (
              <span key={o}><i style={{ background: SWATCH[o] }} />{o.replace(/_/g, " ").toLowerCase()} · {data.outcomes[o]}</span>
            ))}
          </div>
        </div>
      </Panel>

      {live && <LivePanel key={pack} pack={pack} onEnded={reload} />}

      <Panel title="Engine ne kya dekha" hint={`${fmtTime(data.generated_at)} pe bana${live ? " · har 5 s refresh" : ""}`}>
        <div className="body">
          {data.insights.length === 0 && <p className="muted">Abhi kuch kehne layak nahi — kuch calls hone do.</p>}
          {data.insights.map((line, i) => <p key={i} data-reveal style={{ "--i": i, margin: "6px 0" } as CSSProperties}>• {line}</p>)}
        </div>
      </Panel>
    </Page>
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
                <span className="mono">{s.channel.toLowerCase()}{s.phone ? ` · ${s.phone}` : ""} · {s.turns} turns</span>
                <span className="muted">{s.last_caller ? `“${s.last_caller}”` : "—"}</span>
                {s.human
                  ? <button className="btn btn-ghost btn-sm" onClick={() => engine.handback(s.sid).then(refreshSessions)}>Wapas agent ko</button>
                  : <button className="btn btn-primary btn-sm" onClick={() => engine.takeover(s.sid).then(refreshSessions)}>Mujhe do</button>}
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
          <p className="muted">Ek call karke dekho — <a href="/engine/talk" target="_blank" rel="noopener noreferrer">/talk</a> ya WhatsApp simulator se. Har turn yahan turant aayega.</p>
        )}
        {events.map((e) => (
          <div key={e.seq} className={"ev " + e.kind.replace(".", "-")}>
            <span className="when mono">{fmtTime(e.at)}</span>
            {e.kind === "session.started" && <span>Call shuru · {e.channel?.toLowerCase()}{e.phone ? ` · ${e.phone}` : ""} — <em>{e.greeting}</em></span>}
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
        ))}
      </div>
    </Panel>
  );
}
