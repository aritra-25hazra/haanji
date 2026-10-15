import { useEffect, type CSSProperties } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { engine } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Loading, Page, Panel, Tile, fmtInr, fmtTime, useData } from "../components/Common";

const ORDER = ["BOOKED", "FAQ_ANSWERED", "LEAD_CAPTURED", "HANDED_OFF", "ABANDONED", "IN_PROGRESS"];
const SWATCH: Record<string, string> = {
  BOOKED: "var(--leaf-ink)", FAQ_ANSWERED: "var(--cobalt)", LEAD_CAPTURED: "var(--marigold)",
  HANDED_OFF: "var(--sindoor-ink)", ABANDONED: "var(--ink-2)", IN_PROGRESS: "var(--ink-2)",
};

export default function Dashboard() {
  const { pack, online } = useApp();
  const { data, loading, error, reload } = useData(
    () => (online ? engine.insights(pack) : Promise.resolve(sample.insights())), [pack, online]);
  useEffect(() => {
    if (!online) return;
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
  }, [online, reload]);

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
  const present = ORDER.filter((o) => data.outcomes[o]);

  return (
    <Page title="Aaj" sub={`${pack.replace(/_/g, " ")} — har call jo agent ne uthayi, aur usse kya nikla.`}>
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
          <div className="obar" role="img" aria-label={present.map((o) => `${o.toLowerCase()} ${data.outcomes[o]}`).join(", ")}>
            {present.map((o) => <i key={o} className={o} style={{ width: `${((data.outcomes[o] ?? 0) / total) * 100}%` }} />)}
          </div>
          <div className="legend">
            {present.map((o) => (
              <span key={o}><i style={{ background: SWATCH[o] }} />{o.replace(/_/g, " ").toLowerCase()} · {data.outcomes[o]}</span>
            ))}
          </div>
        </div>
      </Panel>

      <Panel title="Engine ne kya dekha" hint={`${fmtTime(data.generated_at)} pe bana${online ? " · har 5 s refresh" : ""}`}>
        <div className="body">
          {data.insights.length === 0 && <p className="muted">Abhi kuch kehne layak nahi — kuch calls hone do.</p>}
          {data.insights.map((line, i) => <p key={i} data-reveal style={{ "--i": i, margin: "6px 0" } as CSSProperties}>• {line}</p>)}
        </div>
      </Panel>
    </Page>
  );
}
