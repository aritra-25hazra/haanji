import { useMemo, useState, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { engine } from "../engine";
import { OUTCOME_LABEL, businessName } from "../labels";
import { sample } from "../sample";
import { useApp } from "../state";
import { en, t, tn, useT } from "../i18n";
import { Empty, Icon, Loading, NotLive, OutcomeChip, Page, Panel, Register, fmtDate, fmtTime, istDay, rowButton, useData } from "../components/Common";

const SUB = en("Newest first. Open a row for the transcript and the receipt.");
const CHANNEL: Record<string, string> = { PHONE: en("Phone"), WHATSAPP: "WhatsApp", WEB: en("Web") };

export default function Calls() {
  const { pack, mode } = useApp();
  useT();
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

  if (!live && mode !== "demo") return <NotLive title={t("Calls")} sub={t(SUB)} />;
  if (loading && !data) return <Loading kind="table" />;
  if (!data) {
    return (
      <Page title={t("Calls")}>
        <Empty>{t("Could not load: {error}", { error: error ?? "" })}<button className="btn btn-ghost btn-sm" onClick={reload}>{t("Try again")}</button></Empty>
      </Page>
    );
  }
  const filtered = shown.length !== data.length;

  return (
    <Page title={t("Calls")} sub={t(SUB)}>
      <div className="filters" role="search" aria-label={t("Filter calls")}>
        <label className="field"><span>{t("Result")}</span>
          <select className="input" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="ALL">{t("All")}</option>
            {Object.entries(OUTCOME_LABEL).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
          </select></label>
        <label className="field"><span>{t("From")}</span>
          <select className="input" value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option value="ALL">{t("All")}</option>
            {Object.entries(CHANNEL).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
          </select></label>
        <label className="field"><span>{t("Day")}</span>
          <input className="input" type="date" value={day} onChange={(e) => setDay(e.target.value)} /></label>
        <label className="field grow"><span>{t("Number")}</span>
          <input className="input" inputMode="numeric" placeholder={t("last digits")} value={number} onChange={(e) => setNumber(e.target.value)} /></label>
        {(outcome !== "ALL" || channel !== "ALL" || day || number) && (
          <button className="btn btn-ghost btn-sm" onClick={() => { setOutcome("ALL"); setChannel("ALL"); setDay(""); setNumber(""); }}>{t("Clear")}</button>
        )}
      </div>
      <Panel title={live ? t("All calls") : t("Sample calls")} hint={(filtered ? tn("{n} of {total} call", "{n} of {total} calls", data.length, { n: shown.length, total: data.length }) : tn("{n} call", "{n} calls", data.length)) + " · " + businessName(pack)}>
        {data.length === 0 ? (
          <Empty>
            <p>{t("No calls yet.")}</p>
            <a className="btn btn-primary" href="/engine/talk" target="_blank" rel="noopener noreferrer">{t("Try a call on /talk")} <Icon name="external" small /></a>
          </Empty>
        ) : shown.length === 0 ? (
          <Empty><p>{t("No calls match these filters.")}</p></Empty>
        ) : (
          <Register cards head={<><th>{t("When")}</th><th>{t("From")}</th><th>{t("Number")}</th><th>{t("Result")}</th><th className="right">{t("Misheard, fixed")}</th></>}>
            {shown.map((c, i) => (
              <tr key={c.call_id} {...rowButton(() => nav(`/calls/${c.call_id}`), t("Open the call of {when}", { when: `${fmtDate(c.started_at)} ${fmtTime(c.started_at)}` }))}
                  data-reveal style={{ "--i": Math.min(i, 20) } as CSSProperties}>
                <td className="mono">{fmtDate(c.started_at)} {fmtTime(c.started_at)}</td>
                <td>{CHANNEL[c.channel] ? t(CHANNEL[c.channel]!) : c.channel.toLowerCase()}</td>
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
