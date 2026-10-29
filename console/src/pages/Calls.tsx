import type { CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { engine, fmtMs } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Empty, Icon, Loading, NotLive, OutcomeChip, Page, Panel, Register, fmtDate, fmtTime, rowButton, useData } from "../components/Common";

const SUB = "Nayi pehle. Transcript aur receipt ke liye row kholo.";

export default function Calls() {
  const { pack, mode } = useApp();
  const nav = useNavigate();
  const live = mode === "live";
  const loader = live ? () => engine.calls(pack).then((r) => r.conversations) : mode === "demo" ? () => Promise.resolve(sample.calls()) : null;
  const { data, loading, error, reload } = useData(loader, [pack, mode]);

  if (!live && mode !== "demo") return <NotLive title="Calls" sub={SUB} />;
  if (loading && !data) return <Loading />;
  if (!data) {
    return (
      <Page title="Calls">
        <Empty>Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty>
      </Page>
    );
  }

  return (
    <Page title="Calls" sub={SUB}>
      <Panel title={live ? "Engine ki calls" : "Sample calls"} hint={`${data.length} calls · ${pack.replace(/_/g, " ")}`}>
        {data.length === 0 ? (
          <Empty>
            <p>Abhi koi call nahi.</p>
            <a className="btn btn-primary" href="/engine/talk" target="_blank" rel="noopener noreferrer">/talk pe ek call karke dekho <Icon name="external" small /></a>
          </Empty>
        ) : (
          <Register head={<><th>Kab</th><th>Channel</th><th>Caller</th><th>Outcome</th><th className="right">Repairs</th><th className="right">Spec hits</th><th className="right">Latency p50</th></>}>
            {data.map((c, i) => (
              <tr key={c.call_id} {...rowButton(() => nav(`/calls/${c.call_id}`), `Call ${fmtDate(c.started_at)} ${fmtTime(c.started_at)} kholo`)}
                  data-reveal style={{ "--i": i } as CSSProperties}>
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
