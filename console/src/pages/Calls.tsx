import { useMemo, useState, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { engine } from "../engine";
import { OUTCOME_LABEL, businessName } from "../labels";
import { sample } from "../sample";
import { useApp } from "../state";
import { Empty, Icon, Loading, NotLive, OutcomeChip, Page, Panel, Register, fmtDate, fmtTime, istDay, rowButton, useData } from "../components/Common";

const SUB = "Nayi pehle. Transcript aur receipt ke liye row kholo.";
const CHANNEL: Record<string, string> = { PHONE: "Phone", WHATSAPP: "WhatsApp", WEB: "Web" };

export default function Calls() {
  const { pack, mode } = useApp();
  const nav = useNavigate();
  const live = mode === "live";
  const loader = live ? () => engine.calls(pack, 500).then((r) => r.conversations) : mode === "demo" ? () => Promise.resolve(sample.calls(pack)) : null;
  const { data, loading, error, reload } = useData(loader, [pack, mode]);
  const [outcome, setOutcome] = useState("ALL");
  const [channel, setChannel] = useState("ALL");
  const [day, setDay] = useState("");
  const [number, setNumber] = useState("");
  const shown = useMemo(() => {
    const digits = number.replace(/\D/g, "");
    return (data ?? []).filter((c) => (outcome === "ALL" || (c.outcome ?? "IN_PROGRESS") === outcome)
      && (channel === "ALL" || c.channel === channel)
      && (!day || istDay(c.started_at) === day)
      && (!digits || (c.phone ?? "").replace(/\D/g, "").includes(digits)));
  }, [data, outcome, channel, day, number]);

  if (!live && mode !== "demo") return <NotLive title="Calls" sub={SUB} />;
  if (loading && !data) return <Loading kind="table" />;
  if (!data) {
    return (
      <Page title="Calls">
        <Empty>Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty>
      </Page>
    );
  }
  const filtered = shown.length !== data.length;

  return (
    <Page title="Calls" sub={SUB}>
      <div className="filters" role="search" aria-label="Calls chhaano">
        <label className="field"><span>Nateeja</span>
          <select className="input" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="ALL">Sab</option>
            {Object.entries(OUTCOME_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></label>
        <label className="field"><span>Kahan se</span>
          <select className="input" value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option value="ALL">Sab</option>
            {Object.entries(CHANNEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></label>
        <label className="field"><span>Din</span>
          <input className="input" type="date" value={day} onChange={(e) => setDay(e.target.value)} /></label>
        <label className="field grow"><span>Number</span>
          <input className="input" inputMode="numeric" placeholder="aakhri ank" value={number} onChange={(e) => setNumber(e.target.value)} /></label>
        {(outcome !== "ALL" || channel !== "ALL" || day || number) && (
          <button className="btn btn-ghost btn-sm" onClick={() => { setOutcome("ALL"); setChannel("ALL"); setDay(""); setNumber(""); }}>Saaf karo</button>
        )}
      </div>
      <Panel title={live ? "Saari calls" : "Sample calls"} hint={`${filtered ? `${shown.length} of ` : ""}${data.length} calls · ${businessName(pack)}`}>
        {data.length === 0 ? (
          <Empty>
            <p>Abhi koi call nahi.</p>
            <a className="btn btn-primary" href="/engine/talk" target="_blank" rel="noopener noreferrer">/talk pe ek call karke dekho <Icon name="external" small /></a>
          </Empty>
        ) : shown.length === 0 ? (
          <Empty><p>In filters se koi call nahi mili.</p></Empty>
        ) : (
          <Register cards head={<><th>Kab</th><th>Kahan se</th><th>Number</th><th>Nateeja</th><th className="right">Galat suna, theek</th></>}>
            {shown.map((c, i) => (
              <tr key={c.call_id} {...rowButton(() => nav(`/calls/${c.call_id}`), `Call ${fmtDate(c.started_at)} ${fmtTime(c.started_at)} kholo`)}
                  data-reveal style={{ "--i": Math.min(i, 20) } as CSSProperties}>
                <td className="mono">{fmtDate(c.started_at)} {fmtTime(c.started_at)}</td>
                <td>{CHANNEL[c.channel] ?? c.channel.toLowerCase()}</td>
                <td className="mono">{c.phone ?? "—"}</td>
                <td><OutcomeChip outcome={c.outcome} /></td>
                <td className="num right">{c.corrections}</td>
              </tr>
            ))}
          </Register>
        )}
      </Panel>
    </Page>
  );
}
