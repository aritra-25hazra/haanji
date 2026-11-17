import { useEffect } from "react";
import { OpsPreview } from "../components/Preview";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { engine } from "../engine";
import { t, useT } from "../i18n";
import { useApp } from "../state";
import { Chip, Empty, Loading, NotLive, Page, Panel, Register, Tile, Waterfall, fmtTime, useData } from "../components/Common";

const SUB = "Latency objective, traces, counters.";

export default function Ops() {
  const { pack, mode } = useApp();
  useT();
  const live = mode === "live";
  const { data, loading, error, reload } = useData(live ? () => engine.ops(pack) : null, [pack, mode]);
  useEffect(() => {
    if (!live) return;
    const h = setInterval(reload, 10000);
    return () => clearInterval(h);
  }, [live, reload]);

  if (mode === "demo") return <OpsPreview pack={pack} />;
  if (!live) return <NotLive title="Ops" sub={SUB} demo={<p>{t("The Ops view comes from the live engine.")}</p>} />;
  if (loading && !data) return <Loading kind="dashboard" />;
  if (!data) return <Page title="Ops"><Empty>{t("Could not load: {error}", { error: error ?? "" })}<button className="btn btn-ghost btn-sm" onClick={reload}>{t("Retry")}</button></Empty></Page>;

  const slo = data.slo;
  const within = Math.round(slo.within * 100);
  const hit = data.speculation.started ? Math.round((100 * data.speculation.hits) / data.speculation.started) : 0;
  const latest = data.latest_call;
  return (
    <Page title="Ops" sub={t("SLO: every turn within {ms} ms · last {calls} calls, {turns} turns · engine-side time", { ms: slo.target_ms, calls: data.calls, turns: data.turns })}
          actions={<>
            {data.turns
              ? <Chip kind={within >= 99 ? "ok" : within >= 95 ? "warn" : "bad"}>{t("{pct}% of turns within the SLO", { pct: within })}</Chip>
              : <Chip kind="muted">{t("no turns yet")}</Chip>}
            <a className="btn btn-ghost btn-sm" href="/engine/metrics" target="_blank" rel="noopener noreferrer">/metrics (Prometheus)</a>
          </>}>
      <div className="tiles">
        <Tile index={0} label="p50" value={slo.p50} suffix=" ms" mono />
        <Tile index={1} label="p90" value={slo.p90} suffix=" ms" mono foot={slo.p90 <= slo.target_ms ? t("within the SLO") : t("outside the SLO")} />
        <Tile index={2} label="p95" value={slo.p95} suffix=" ms" mono foot={`max ${Math.round(slo.max)} ms`} />
        <Tile index={3} label="Tool turns p90" value={slo.tool_turn_p90} suffix=" ms" mono foot={t("turns that did some work")} />
        <Tile index={4} label="Speculation hit" value={hit} suffix="%" foot={`${data.speculation.hits}/${data.speculation.started} · ${data.speculation.wasted} wasted`} />
        <Tile index={5} label="Live sessions" value={data.live_sessions} foot={`up ${Math.round(data.uptime_s / 60)} min · ${data.providers.llm} llm`} />
      </div>

      <Panel title={t("How turn latency is spread")} hint={data.turns ? t("how many turns in each bucket (ms)") : undefined}>
        {data.turns === 0 ? <Empty><p>{t("No turns yet. Latency shows here after the first call.")}</p></Empty> : <div className="body" style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.histogram} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid stroke="rgba(27,59,140,.14)" vertical={false} />
              <XAxis dataKey="bucket" tickLine={false} axisLine={{ stroke: "rgba(27,59,140,.3)" }} tick={{ fontSize: 12, fill: "rgba(20,33,61,.68)" }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "rgba(20,33,61,.68)" }} allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(27,59,140,.06)" }} contentStyle={{ borderRadius: 8, border: "1px solid rgba(27,59,140,.14)", fontSize: 13 }} />
              <Bar dataKey="turns" name="turns" fill="#1B3B8C" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>}
      </Panel>

      <Panel title={t("Where the time goes")} hint={t("p50 / p90 of each span, over all turns")}>
        <Register head={<><th>Span</th><th className="right">n</th><th className="right">p50</th><th className="right">p90</th></>}>
          {data.spans.map((s) => (
            <tr key={s.name}><td className="mono">{s.name}</td><td className="num right">{s.n}</td><td className="num right">{s.p50} ms</td><td className="num right">{s.p90} ms</td></tr>
          ))}
          {data.spans.length === 0 && <tr><td colSpan={4} className="muted">{t("No turns yet.")}</td></tr>}
        </Register>
      </Panel>

      {latest && (
        <Panel title={t("Trace of the latest call")} hint={`${fmtTime(latest.started_at)} · ${(latest.outcome ?? "in progress").toLowerCase().replace(/_/g, " ")}`}>
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

      <Panel title="Counters" hint={t("what the pager watches (ops/alerts.yml)")}>
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
