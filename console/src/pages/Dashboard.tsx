import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Page, Panel, Stat, useData } from "../components/Common";
import { live, type LiveInsights } from "../live";

const OUTCOME_COLOUR: Record<string, string> = {
  BOOKED: "#0e8f80", FAQ_ANSWERED: "#2c63c4", LEAD_CAPTURED: "#e8952f",
  HANDED_OFF: "#c0392b", ABANDONED: "#9aa7b4",
};

export default function Dashboard() {
  const { data, loading, error } = useData(() => api.dashboard());
  const [ins, setIns] = useState<LiveInsights | null>(null);
  useEffect(() => {
    live.status().then((s) => s && live.insights(s.default_pack).then(setIns));
    const t = setInterval(() => {
      live.status().then((s) => s && live.insights(s.default_pack).then(setIns));
    }, 5000);
    return () => clearInterval(t);
  }, []);
  if (loading) return <div className="empty">Loading…</div>;
  if (error || !data) return <div className="empty">Could not load: {error}</div>;

  const pie = Object.entries(data.outcomes).map(([name, value]) => ({ name, value }));

  return (
    <Page title="Today"
          sub="Every call the agent handled, and what came of it.">
      <p style={{ margin: "-14px 0 18px" }}>
        {ins
          ? <span className="livechip">● live — engine server connected</span>
          : <span className="livechip off">sample data — run `haanji serve` for live numbers</span>}
      </p>
      {ins && (
        <Panel title="AI insights (live)"
               hint={`${ins.calls_total} calls recorded · refreshes every 5 s`}>
          <div className="body">
            <div className="cards" style={{ marginBottom: 16 }}>
              <Stat label="Calls handled" value={ins.calls_total}
                    foot={`${ins.calls_today} today`} />
              <Stat label="Bookings on calendar" value={ins.bookings_confirmed}
                    foot={`worth ₹${ins.revenue_booked_inr.toLocaleString("en-IN")}`} />
              <Stat label="Missed calls recovered"
                    value={`${ins.missed_calls.recovered}/${ins.missed_calls.total}`}
                    foot="via WhatsApp outreach" />
              <Stat label="Cost per call"
                    value={`₹${ins.cost.ai_per_call_inr.toFixed(2)}`}
                    foot={`vs ₹${ins.cost.receptionist_per_call_inr.toFixed(2)} receptionist`} />
              <Stat label="Words repaired" value={ins.corrections_total}
                    foot="Bhasha Bridge" />
              <Stat label="Speculation hit rate"
                    value={`${(ins.speculation.hit_rate * 100).toFixed(0)}%`}
                    foot={`${ins.speculation.hits} of ${ins.speculation.started} tool calls`} />
            </div>
            {ins.insights.map((line, i) => (
              <p key={i} style={{ margin: "6px 0", fontSize: 13.5 }}>• {line}</p>
            ))}
          </div>
        </Panel>
      )}
      <div className="cards">
        <Stat label="Calls answered" value={data.calls_today}
              foot={`${(data.answer_rate * 100).toFixed(0)}% of calls picked up`} />
        <Stat label="Appointments booked" value={data.bookings_today}
              foot={`${(data.booking_rate * 100).toFixed(0)}% of calls ended in a booking`} />
        <Stat label="Leads waiting" value={data.leads_open}
              foot="callers the agent could not book" />
        <Stat label="Reply latency" value={`${data.latency.p50} ms`}
              foot={`p90 ${data.latency.p90} ms · p95 ${data.latency.p95} ms`} />
        <Stat label="Words repaired" value={data.corrections_today}
              foot="Bhasha Bridge, today" />
        <Stat label="Speculation hit rate"
              value={`${(data.speculation_hit_rate * 100).toFixed(0)}%`}
              foot="tools finished before they were asked for" />
      </div>

      <Panel title="Calls through the day" hint="booked calls shown in teal">
        <div className="body" style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.by_hour} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid stroke="#eef2f5" vertical={false} />
              <XAxis dataKey="hour" tickLine={false} axisLine={{ stroke: "#dce2e8" }}
                     tick={{ fontSize: 12, fill: "#5b6875" }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#5b6875" }} />
              <Tooltip cursor={{ fill: "#f6f8fa" }} />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="calls" name="calls" fill="#2c63c4" radius={[3, 3, 0, 0]} />
              <Bar dataKey="booked" name="booked" fill="#0e8f80" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <Panel title="How calls ended">
        <div className="body" style={{ height: 250 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={pie} dataKey="value" nameKey="name" innerRadius={58} outerRadius={92}
                   paddingAngle={2}>
                {pie.map((slice) => (
                  <Cell key={slice.name} fill={OUTCOME_COLOUR[slice.name] ?? "#9aa7b4"} />
                ))}
              </Pie>
              <Tooltip />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </Panel>
    </Page>
  );
}
