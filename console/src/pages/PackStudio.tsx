import { useEffect, useState } from "react";
import { engine } from "../engine";
import { useApp } from "../state";
import { Chip, Empty, Icon, Page, Panel, Register } from "../components/Common";
import type { PackSummary } from "../types";

export default function PackStudio() {
  const { online } = useApp();
  const [packs, setPacks] = useState<PackSummary[] | null>(null);
  const [current, setCurrent] = useState("");
  const [yamlText, setYamlText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [messages, setMessages] = useState<{ kind: "ok" | "bad"; text: string }[]>([]);
  const [results, setResults] = useState<{ passed: boolean; line: string }[]>([]);

  useEffect(() => {
    if (online) engine.packs().then((r) => setPacks(r.packs)).catch(() => setPacks(null));
  }, [online]);

  async function openPack(id: string) {
    const r = await engine.packYaml(id);
    setCurrent(id); setYamlText(r.yaml); setDirty(false); setMessages([]); setResults([]);
  }
  const report = (kind: "ok" | "bad", text: string) => setMessages((m) => [...m, { kind, text }]);

  async function doValidate(): Promise<boolean> {
    setBusy("validating"); setMessages([]);
    try {
      const r = await engine.validate(yamlText);
      if (r.ok) report("ok", "Pack valid hai — koi problem nahi mili."); else r.problems.forEach((p) => report("bad", p));
      return r.ok;
    } catch (e) { report("bad", String((e as Error).message)); return false; }
    finally { setBusy(null); }
  }
  async function doSave() {
    if (!(await doValidate())) return;
    setBusy("saving");
    try {
      const r = await engine.save(current, yamlText);
      report("ok", `Saved. Pichhla version ${r.backup} mein rakha hai.`);
      setDirty(false);
      setPacks((await engine.packs()).packs);
    } catch (e) { report("bad", String((e as Error).message)); }
    finally { setBusy(null); }
  }
  async function doSelftest() {
    setBusy("running scenarios"); setResults([]);
    try {
      const r = await engine.selftest(current);
      setResults(r.results);
      report(r.ok ? "ok" : "bad", r.summary || (r.ok ? "Saare scenarios paas." : "Upar failures dekho."));
    } catch (e) { report("bad", String((e as Error).message)); }
    finally { setBusy(null); }
  }

  if (!online || packs === null) {
    return (
      <Page title="Pack Studio" sub="Ek business type = ek file. Yahin edit, validate aur test hota hai.">
        <Empty><p>Pack Studio live engine ke bina kaam nahi karta — ye files ko sach mein badalta hai.</p></Empty>
      </Page>
    );
  }

  return (
    <Page title="Pack Studio" sub="Edit karo, validate karo, uske apne scenarios chalao — phir ship karo.">
      <Panel title="Installed packs" hint="kholne ke liye click karo">
        <Register head={<><th>Pack</th><th>Language</th><th className="right">Services</th><th className="right">Scenarios</th><th>Health</th></>}>
          {packs.map((p) => (
            <tr key={p.pack_id} className="click" tabIndex={0} onClick={() => openPack(p.pack_id)}
                onKeyDown={(e) => { if (e.key === "Enter") openPack(p.pack_id); }}
                style={p.pack_id === current ? { background: "rgba(245,185,30,.14)" } : undefined}>
              <td><strong>{p.display_name}</strong> <span className="muted mono" style={{ fontSize: 12 }}>v{p.version}</span></td>
              <td>{p.language}</td>
              <td className="num right">{p.services}</td>
              <td className="num right">{p.scenarios}</td>
              <td>{p.issues.length === 0 ? <Chip kind="ok">valid</Chip> : <Chip kind="bad">{p.issues.length} issues</Chip>}</td>
            </tr>
          ))}
        </Register>
      </Panel>

      {current && (
        <Panel title={`${current}.yaml`} hint={dirty ? "unsaved changes" : "disk ke saath sync"}>
          <div className="body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <textarea className="input" value={yamlText} onChange={(e) => { setYamlText(e.target.value); setDirty(true); }}
                      spellCheck={false} style={{ height: 440 }} aria-label="Pack YAML" />
            <div className="row">
              <button className="btn btn-ghost" onClick={doValidate} disabled={busy !== null}>Validate</button>
              <button className="btn btn-primary" onClick={doSave} disabled={busy !== null}>Validate &amp; save</button>
              <button className="btn btn-ghost" onClick={doSelftest} disabled={busy !== null}><Icon name="bolt" small />Is pack ke scenarios chalao</button>
              <a className="btn btn-ghost" href="/engine/talk" target="_blank" rel="noopener noreferrer">Try it live <Icon name="external" small /></a>
              {busy && <span className="muted">{busy}…</span>}
            </div>
            {messages.length > 0 && (
              <div className="row">
                {messages.map((m, i) => <Chip key={i} kind={m.kind === "ok" ? "ok" : "bad"}><Icon name={m.kind === "ok" ? "check" : "x"} small />{m.text}</Chip>)}
              </div>
            )}
            {results.length > 0 && (
              <Register head={<><th>Scenario run</th><th>Result</th></>}>
                {results.map((r, i) => (
                  <tr key={i}>
                    <td className="mono" style={{ fontSize: 12.5 }}>{r.line}</td>
                    <td>{r.passed ? <Chip kind="ok">pass</Chip> : <Chip kind="bad">fail</Chip>}</td>
                  </tr>
                ))}
              </Register>
            )}
          </div>
        </Panel>
      )}
    </Page>
  );
}
