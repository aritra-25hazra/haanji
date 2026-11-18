import { useEffect, useState, type CSSProperties } from "react";
import { engine } from "../engine";
import { sample } from "../sample";
import { en, t, useT } from "../i18n";
import { useApp } from "../state";
import { Chip, Empty, Icon, Loading, NotLive, Page, Panel, Register, useData, type ChipKind } from "../components/Common";

const KIND: Record<string, ChipKind | undefined> = {
  SERVICE: "ok", STAFF: undefined, PLACE: "warn", BRAND: "muted", PHRASE: "muted",
};
const SUB = en("This business's own words, indexed by how they sound. The list builds itself from the catalogue; nobody types it.");

export default function Lexicon() {
  const { pack, mode } = useApp();
  useT();
  const [probe, setProbe] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const h = setTimeout(() => setDebounced(probe.trim()), 300); return () => clearTimeout(h); }, [probe]);

  const live = mode === "live";
  const loader = live ? () => engine.lexicon(pack, debounced || undefined) : mode === "demo" ? () => Promise.resolve(sample.lexicon(pack)) : null;
  const { data, loading, error, reload } = useData(loader, [pack, mode, debounced]);

  if (!live && mode !== "demo") return <NotLive title="Bhasha lexicon" sub={t(SUB)} kind="table" />;
  if (loading && !data) return <Loading kind="table" />;
  if (!data) {
    return (
      <Page title="Bhasha lexicon">
        <Empty>{t("Could not load: {error}", { error: error ?? "" })}<button className="btn btn-ghost btn-sm" onClick={reload}>{t("Try again")}</button></Empty>
      </Page>
    );
  }

  return (
    <Page title="Bhasha lexicon" sub={t(SUB)}>
      <Panel title={t("Type what was heard")} hint={live ? t("the engine shows where this sound lands") : t("needs the live engine")}>
        <div className="body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <input className="input" value={probe} onChange={(e) => setProbe(e.target.value)} disabled={!live}
                 placeholder={t("e.g. \"rut kanal\" or \"sheikh\"")} aria-label={t("Phrase as heard")} style={{ maxWidth: 420 }} />
          {data.probe && (
            <div className="row" style={{ fontSize: 15 }}>
              <span>"{data.probe.text}"</span><Icon name="arrow" small />
              <Chip mono>{data.probe.key || "—"}</Chip><Icon name="arrow" small />
              {data.probe.matches.length
                ? data.probe.matches.map((m) => <Chip key={m} kind="ok"><Icon name="check" small />{m}</Chip>)
                : <Chip kind="muted">{t("no entry for this sound")}</Chip>}
            </div>
          )}
        </div>
      </Panel>

      <Panel title="Vocabulary" hint={`${data.entries.length} entries · v${data.version}`}>
        <Register head={<><th>{t("Word")}</th><th>Kind</th><th>{t("Also heard as")}</th><th>Sound key</th><th className="right">Weight</th></>}>
          {data.entries.map((e, i) => (
            <tr key={e.surface + i} data-reveal style={{ "--i": Math.min(i, 20) } as CSSProperties}>
              <td><strong>{e.surface}</strong></td>
              <td><Chip kind={KIND[e.entry_type]}>{e.entry_type.toLowerCase()}</Chip></td>
              <td className="muted">{e.variants.join(", ") || "—"}</td>
              <td className="mono">{e.keys.join(" · ")}</td>
              <td className="num right">{e.weight.toFixed(2)}</td>
            </tr>
          ))}
        </Register>
      </Panel>

      <Panel title={t("When a repair happens")}>
        <div className="body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p>{t("A word is changed only when two separate things are true together: the recogniser was not sure of it (confidence below 0.85), and its sound key matches an entry in this list exactly, within a small spelling distance. Either one alone gives wrong corrections, and a layer that spoils a good transcript is worse than none.")}</p>
          <p className="muted">{t("A name the caller has just given is never touched, however it sounds.")}</p>
        </div>
      </Panel>
    </Page>
  );
}
