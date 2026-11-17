import type { CSSProperties } from "react";
import { engine } from "../engine";
import { sample } from "../sample";
import { en, t, useT } from "../i18n";
import { useApp } from "../state";
import { Chip, Empty, Loading, NotLive, Page, Panel, Register, useData } from "../components/Common";

const SUB = en("One file says what the agent knows, what it declines, and how it speaks.");

export default function Packs() {
  const { pack, mode, setPack } = useApp();
  useT();
  const live = mode === "live";
  const loader = live ? () => engine.packs().then((r) => r.packs) : mode === "demo" ? () => Promise.resolve(sample.packs()) : null;
  const { data, loading, error, reload } = useData(loader, [mode]);

  if (!live && mode !== "demo") return <NotLive title="Vertical packs" sub={t(SUB)} />;
  if (loading && !data) return <Loading kind="table" />;
  if (!data) {
    return (
      <Page title="Packs">
        <Empty>{t("Could not load: {error}", { error: error ?? "" })}<button className="btn btn-ghost btn-sm" onClick={reload}>{t("Try again")}</button></Empty>
      </Page>
    );
  }

  return (
    <Page title="Vertical packs" sub={t(SUB)}>
      <Panel title="Installed" hint={`${data.length} packs`}>
        <Register head={<><th>Pack</th><th>Language</th><th className="right">Services</th><th className="right">Staff</th><th className="right">Scenarios</th><th>Health</th><th></th></>}>
          {data.map((p, i) => (
            <tr key={p.pack_id} data-reveal style={{ "--i": i } as CSSProperties}>
              <td><strong>{p.display_name}</strong> <span className="muted mono" style={{ fontSize: 12 }}>v{p.version}</span></td>
              <td>{p.language}</td>
              <td className="num right">{p.services}</td>
              <td className="num right">{p.staff}</td>
              <td className="num right">{p.scenarios}</td>
              <td>{p.issues.length === 0 ? <Chip kind="ok">valid</Chip> : <Chip kind="bad">{p.issues.length} issues</Chip>}</td>
              <td className="right">{p.pack_id === pack ? <Chip kind="warn">in use</Chip> : <button className="btn btn-ghost btn-sm" onClick={() => setPack(p.pack_id)}>Use</button>}</td>
            </tr>
          ))}
        </Register>
      </Panel>

      <Panel title={t("What a pack holds")}>
        <div className="body">
          <dl style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: "8px 16px", margin: 0 }}>
            <dt className="muted">Catalogue</dt><dd style={{ margin: 0 }}>{t("services, how long, price, who does it")}</dd>
            <dt className="muted">Hours</dt><dd style={{ margin: 0 }}>{t("days, opening and closing times, breaks")}</dd>
            <dt className="muted">Persona</dt><dd style={{ margin: 0 }}>{t("greeting, tone, how much to say at once")}</dd>
            <dt className="muted">Guardrails</dt><dd style={{ margin: 0 }}>{t("what to decline outright, what to pass to a person")}</dd>
            <dt className="muted">Vocabulary</dt><dd style={{ margin: 0 }}>{t("seed words for the sound index: areas, brands, common phrases")}</dd>
            <dt className="muted">Knowledge</dt><dd style={{ margin: 0 }}>{t("the questions people really ask, and the answers")}</dd>
            <dt className="muted">Scenarios</dt><dd style={{ margin: 0 }}>{t("the calls a pack must pass before it ships")}</dd>
          </dl>
        </div>
      </Panel>
    </Page>
  );
}
