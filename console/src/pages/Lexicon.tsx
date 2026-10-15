import { useEffect, useState, type CSSProperties } from "react";
import { engine } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Chip, Empty, Icon, Loading, Page, Panel, Register, useData } from "../components/Common";

const KIND: Record<string, "ok" | "warn" | "bad" | "muted" | undefined> = {
  SERVICE: "ok", STAFF: undefined, PLACE: "warn", BRAND: "muted", PHRASE: "muted",
};

export default function Lexicon() {
  const { pack, online } = useApp();
  const [probe, setProbe] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(probe.trim()), 300); return () => clearTimeout(t); }, [probe]);

  const { data, loading, error, reload } = useData(
    () => (online ? engine.lexicon(pack, debounced || undefined) : Promise.resolve(sample.lexicon())), [pack, online, debounced]);

  if (loading && !data) return <Loading />;
  if (!data) {
    return (
      <Page title="Bhasha lexicon">
        <Empty>Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty>
      </Page>
    );
  }

  return (
    <Page title="Bhasha lexicon" sub="Is business ke apne shabd, awaaz ke hisaab se indexed. Catalogue se khud banta hai — ye list koi type nahi karta.">
      <Panel title="Jo suna gaya, wo likho" hint={online ? "engine batayega ye awaaz kahan land karti hai" : "live engine chahiye"}>
        <div className="body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <input className="input" value={probe} onChange={(e) => setProbe(e.target.value)} disabled={!online}
                 placeholder='jaise "rut kanal" ya "sheikh"' aria-label="Suna hua phrase" style={{ maxWidth: 420 }} />
          {data.probe && (
            <div className="row" style={{ fontSize: 15 }}>
              <span>"{data.probe.text}"</span><Icon name="arrow" small />
              <Chip mono>{data.probe.key || "—"}</Chip><Icon name="arrow" small />
              {data.probe.matches.length
                ? data.probe.matches.map((m) => <Chip key={m} kind="ok"><Icon name="check" small />{m}</Chip>)
                : <Chip kind="muted">koi entry is awaaz pe nahi</Chip>}
            </div>
          )}
        </div>
      </Panel>

      <Panel title="Vocabulary" hint={`${data.entries.length} entries · v${data.version}`}>
        <Register head={<><th>Shabd</th><th>Kind</th><th>Aise bhi suna</th><th>Sound key</th><th className="right">Weight</th></>}>
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

      <Panel title="Ek repair kab hota hai">
        <div className="body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p>Ek shabd tabhi badla jaata hai jab do alag-alag cheezein ek saath sach hon: recogniser us shabd pe <strong>sure nahi</strong> tha (confidence 0.85 se kam), <em>aur</em> uski sound key is list ki kisi entry se <strong>bilkul match</strong> karti hai, chhoti si spelling doori ke andar. Dono mein se koi ek akela galat corrections deta hai — aur jo layer achhe transcript ko bigaade, wo na hone se buri hai.</p>
          <p className="muted">Caller ne abhi-abhi jo naam bataya, usse kabhi nahi chheda jaata, chahe wo kaisa bhi sune.</p>
        </div>
      </Panel>
    </Page>
  );
}
