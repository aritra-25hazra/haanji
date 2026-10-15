import type { CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { engine, fmtMs } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Empty, Icon, Loading, OutcomeChip, Page, Panel, Register, fmtDate, fmtTime, useData } from "../components/Common";

export default function Calls() {
  const { pack, online } = useApp();
  const nav = useNavigate();
  const { data, loading, error, reload } = useData(
    () => (online ? engine.calls(pack).then((r) => r.conversations) : Promise.resolve(sample.calls())), [pack, online]);

  if (loading && !data) return <Loading />;
  if (!data) {
    return (
      <Page title="Calls">
        <Empty>Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty>
      </Page>
    );
  }

  return (
    <Page title="Calls" sub="Nayi pehle. Transcript aur receipt ke liye row kholo.">
      <Panel title={online ? "Engine ki calls" : "Sample calls"} hint={`${data.length} calls · ${pack.replace(/_/g, " ")}`}>
        {data.length === 0 ? (
          <Empty>
            <p>Abhi koi call nahi.</p>
            <a className="btn btn-primary" href="/engine/talk" target="_blank" rel="noopener noreferrer">/talk pe ek call karke dekho <Icon name="external" small /></a>
          </Empty>
        ) : (
          <Register head={<><th>Kab</th><th>Channel</th><th>Caller</th><th>Outcome</th><th className="right">Repairs</th><th className="right">Spec hits</th><th className="right">Latency p50</th></>}>
            {data.map((c, i) => (
              <tr key={c.call_id} className="click" data-reveal style={{ "--i": i } as CSSProperties}
                  onClick={() => nav(`/calls/${c.call_id}`)} tabIndex={0}
                  onKeyDown={(e) => { if (e.key === "Enter") nav(`/calls/${c.call_id}`); }}>
                <td className="mono">{fmtDate(c.started_at)} {fmtTime(c.started_at)}</td>
                <td>{c.channel.toLowerCase()}</td>
                <td className="mono">{c.phone ?? "—"}</td>
                <td><OutcomeChip outcome={c.outcome} /></td>
                <td className="num right">{c.corrections}</td>
                <td className="num right">{c.spec_hits}{c.spec_started != null ? `/${c.spec_started}` : ""}</td>
                <td className="num right">{fmtMs(c.latency_p50)}</td>
              </tr>
            ))}
          </Register>
        )}
      </Panel>
    </Page>
  );
}
