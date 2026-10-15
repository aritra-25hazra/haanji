import { useEffect } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { engine } from "../engine";
import { useApp } from "../state";
import { Chip, Empty, Loading, Page, Panel, Register, Tile, Waterfall, fmtTime, useData } from "../components/Common";

export default function Ops() {
  const { pack, online } = useApp();
  const { data, loading, error, reload } = useData(() => (online ? engine.ops(pack) : Promise.resolve(null)), [pack, online]);
  useEffect(() => {
    if (!online) return;
    const t = setInterval(reload, 10000);
    return () => clearInterval(t);
  }, [online, reload]);

  if (!online) return <Page title="Ops" sub="Latency objective, traces, counters."><Empty><p>Ops view live engine se aata hai.</p></Empty></Page>;
  if (loading && !data) return <Loading />;
  if (!data) return <Page title="Ops"><Empty>Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara</button></Empty></Page>;

  const slo = data.slo;
  const within = Math.round(slo.within * 100);
  const hit = data.speculation.started ? Math.round((100 * data.speculation.hits) / data.speculation.started) : 0;
  const latest = data.latest_call;
  return (
    <Page title="Ops" sub={`SLO: har turn ${slo.target_ms} ms ke andar · pichhli ${data.calls} calls, ${data.turns} turns · engine-side time`}
          actions={<>
            <Chip kind={within >= 99 ? "ok" : within >= 95 ? "warn" : "bad"}>{within}% turns SLO ke andar</Chip>
            <a className="btn btn-ghost btn-sm" href="/engine/metrics" target="_blank" rel="noopener noreferrer">/metrics (Prometheus)</a>
          </>}>
      <div className="tiles">
        <Tile index={0} label="p50" value={slo.p50} suffix=" ms" mono />
        <Tile index={1} label="p90" value={slo.p90} suffix=" ms" mono foot={slo.p90 <= slo.target_ms ? "SLO ke andar" : "SLO ke bahar"} />
        <Tile index={2} label="p95" value={slo.p95} suffix=" ms" mono foot={`max ${Math.round(slo.max)} ms`} />
        <Tile index={3} label="Tool turns p90" value={slo.tool_turn_p90} suffix=" ms" mono foot="jin turns mein kaam tha" />
        <Tile index={4} label="Speculation hit" value={hit} suffix="%" foot={`${data.speculation.hits}/${data.speculation.started} · ${data.speculation.wasted} wasted`} />
        <Tile index={5} label="Live sessions" value={data.live_sessions} foot={`up ${Math.round(data.uptime_s / 60)} min · ${data.providers.llm} llm`} />
      </div>

      <Panel title="Turn latency ka batwara" hint="kitne turns kis bucket mein (ms)">
        <div className="body" style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.histogram} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid stroke="rgba(27,59,140,.14)" vertical={false} />
              <XAxis dataKey="bucket" tickLine={false} axisLine={{ stroke: "rgba(27,59,140,.3)" }} tick={{ fontSize: 12, fill: "rgba(20,33,61,.68)" }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "rgba(20,33,61,.68)" }} allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(27,59,140,.06)" }} contentStyle={{ borderRadius: 8, border: "1px solid rgba(27,59,140,.14)", fontSize: 13 }} />
              <Bar dataKey="turns" name="turns" fill="#1B3B8C" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <Panel title="Time kahan jaata hai" hint="har span ka p50 / p90, saari turns pe">
        <Register head={<><th>Span</th><th className="right">n</th><th className="right">p50</th><th className="right">p90</th></>}>
          {data.spans.map((s) => (
            <tr key={s.name}><td className="mono">{s.name}</td><td className="num right">{s.n}</td><td className="num right">{s.p50} ms</td><td className="num right">{s.p90} ms</td></tr>
          ))}
          {data.spans.length === 0 && <tr><td colSpan={4} className="muted">Abhi koi turn nahi.</td></tr>}
        </Register>
      </Panel>

      {latest && (
        <Panel title="Sabse nayi call ka trace" hint={`${fmtTime(latest.started_at)} · ${(latest.outcome ?? "in progress").toLowerCase().replace(/_/g, " ")}`}>
          <div className="body traces">
            {latest.turns.map((t, i) => (
              <div key={i} className="trace">
                <p className="trace-head"><span className="mono muted">turn {i + 1}</span> “{t.corrected || t.heard}” <span className="mono muted">{Math.round(t.latency_ms ?? 0)} ms</span></p>
                <Waterfall spans={t.spans ?? []} total={t.latency_ms} />
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel title="Counters" hint="jo pager dekhta hai (ops/alerts.yml)">
        <div className="body row counters">
          <Chip kind={data.counters.unconfirmed_refused ? "bad" : "ok"}>unconfirmed writes refused · {data.counters.unconfirmed_refused}</Chip>
          <Chip kind={data.counters.rate_limited ? "warn" : undefined}>429 · {data.counters.rate_limited}</Chip>
          <Chip kind={data.counters.auth_denied ? "warn" : undefined}>401/403 · {data.counters.auth_denied}</Chip>
          <Chip kind={data.counters.adapter_fallbacks ? "warn" : undefined}>model fallbacks · {data.counters.adapter_fallbacks}</Chip>
          <Chip>events · {data.counters.events}</Chip>
        </div>
      </Panel>
    </Page>
  );
}
