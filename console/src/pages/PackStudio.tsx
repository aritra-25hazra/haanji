import { useEffect, useState } from "react";
import { engine } from "../engine";
import { useApp } from "../state";
import { Chip, Empty, Icon, Loading, NotLive, Page, Panel, Register, rowButton } from "../components/Common";
import type { PackSummary } from "../types";

const SUB = "Edit karo, validate karo, uske apne scenarios chalao — phir ship karo.";

export default function PackStudio() {
  const { mode, isOwner } = useApp();
  const live = mode === "live";
  const [packs, setPacks] = useState<PackSummary[] | null>(null);
  const [packsError, setPacksError] = useState<string | null>(null);
  const [current, setCurrent] = useState("");
  const [yamlText, setYamlText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [messages, setMessages] = useState<{ kind: "ok" | "bad"; text: string }[]>([]);
  const [results, setResults] = useState<{ passed: boolean; line: string }[]>([]);

  useEffect(() => {
    if (!live) return;
    let alive = true;
    engine.packs().then((r) => { if (alive) setPacks(r.packs); }).catch((e: Error) => { if (alive) setPacksError(e.message); });
    return () => { alive = false; };
  }, [live]);

  async function openPack(id: string) {
    try {
      const r = await engine.packYaml(id);
      setCurrent(id); setYamlText(r.yaml); setDirty(false); setMessages([]); setResults([]);
    } catch (e) { setMessages([{ kind: "bad", text: (e as Error).message }]); }
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

  if (!live) return <NotLive title="Pack Studio" sub={SUB} demo={<p>Pack Studio live engine ke bina kaam nahi karta — ye files ko sach mein badalta hai.</p>} />;
  if (packs === null) {
    return (
      <Page title="Pack Studio" sub={SUB}>
        {packsError ? <Empty>Packs load nahi hue: {packsError}</Empty> : <Loading />}
      </Page>
    );
  }

  return (
    <Page title="Pack Studio" sub={SUB}>
      <Panel title="Installed packs" hint="kholne ke liye row chuno">
        <Register head={<><th>Pack</th><th>Language</th><th className="right">Services</th><th className="right">Scenarios</th><th>Health</th></>}>
          {packs.map((p) => (
            <tr key={p.pack_id} {...rowButton(() => void openPack(p.pack_id), `${p.display_name} kholo`)}
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
                      spellCheck={false} style={{ height: 440 }} aria-label="Pack YAML" readOnly={!isOwner} />
            <div className="row">
              <button className="btn btn-ghost" onClick={() => void doValidate()} disabled={busy !== null}>Validate</button>
              {isOwner
                ? <button className="btn btn-primary" onClick={() => void doSave()} disabled={busy !== null}>Validate &amp; save</button>
                : <Chip kind="muted" title="Pack files sirf owner badal sakta hai">save sirf owner</Chip>}
              <button className="btn btn-ghost" onClick={() => void doSelftest()} disabled={busy !== null}><Icon name="bolt" small />Is pack ke scenarios chalao</button>
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
