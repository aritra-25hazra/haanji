import { useEffect, useState } from "react";
import { Page, Panel } from "../components/Common";
import { live, type PackSummary } from "../live";

/**
 * Pack Studio: edit a vertical pack as YAML with a guarded save.
 *
 * Deliberately YAML-first rather than a form for every field — a pack is a
 * document its author reads top to bottom, and the safety comes from the
 * server: validate before save, an automatic .bak of the previous version,
 * and the pack's own scenarios runnable in one click. Nothing ships until
 * its calls still reach the expected outcome.
 */
export default function PackStudio() {
  const [packs, setPacks] = useState<PackSummary[] | null>(null);
  const [current, setCurrent] = useState<string>("");
  const [yamlText, setYamlText] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [messages, setMessages] = useState<{ kind: "ok" | "bad" | "info"; text: string }[]>([]);
  const [scenarioRows, setScenarioRows] = useState<{ passed: boolean; line: string }[]>([]);

  useEffect(() => {
    live.packs().then((p) => setPacks(p ? p.packs : null));
  }, []);

  async function openPack(id: string) {
    const res = await live.packYaml(id);
    if (!res) return;
    setCurrent(id);
    setYamlText(res.yaml);
    setDirty(false);
    setMessages([]);
    setScenarioRows([]);
  }

  function report(kind: "ok" | "bad" | "info", text: string) {
    setMessages((m) => [...m, { kind, text }]);
  }

  async function doValidate(): Promise<boolean> {
    setBusy("validating");
    setMessages([]);
    try {
      const r = await live.validate(yamlText);
      if (r.ok) report("ok", "Pack valid hai — koi problem nahi mili.");
      else r.problems.forEach((p) => report("bad", p));
      return r.ok;
    } catch (e) {
      report("bad", String(e));
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function doSave() {
    if (!(await doValidate())) return;
    setBusy("saving");
    try {
      const r = await live.save(current, yamlText);
      report("ok", `Saved. Pichhla version ${r.backup} me rakha hai.`);
      setDirty(false);
      const p = await live.packs();
      if (p) setPacks(p.packs);
    } catch (e) {
      report("bad", String(e));
    } finally {
      setBusy(null);
    }
  }

  async function doSelftest() {
    setBusy("running scenarios");
    setScenarioRows([]);
    try {
      const r = await live.selftest(current);
      setScenarioRows(r.results);
      report(r.ok ? "ok" : "bad", r.summary || (r.ok ? "All scenarios passed." : "Failures above."));
    } catch (e) {
      report("bad", String(e));
    } finally {
      setBusy(null);
    }
  }

  if (packs === null) {
    return (
      <Page title="Pack Studio" sub="Ek business type = ek file. Yahin edit, validate aur test hota hai.">
        <div className="empty">
          Engine server nahi mila. <code>haanji serve</code> chala kar refresh kijiye —
          Pack Studio live server ke bina kaam nahi karta (yeh files ko sach me badalta hai).
        </div>
      </Page>
    );
  }

  return (
    <Page title="Pack Studio"
          sub="Ek business type = ek file. Edit karo, validate karo, uske apne scenarios chalao — phir ship karo.">
      <Panel title="Installed packs" hint="click to open">
        <table>
          <thead>
            <tr><th>Pack</th><th>Language</th><th>Services</th><th>Scenarios</th><th>Health</th></tr>
          </thead>
          <tbody>
            {packs.map((p) => (
              <tr key={p.pack_id} onClick={() => openPack(p.pack_id)}
                  style={{ cursor: "pointer", background: p.pack_id === current ? "#eef4fb" : undefined }}>
                <td><strong>{p.display_name}</strong> <span style={{ color: "#8a96a3" }}>v{p.version}</span></td>
                <td>{p.language}</td>
                <td>{p.services}</td>
                <td>{p.scenarios}</td>
                <td>{p.issues.length === 0
                  ? <span className="badge BOOKED">valid</span>
                  : <span className="badge HANDED_OFF">{p.issues.length} issues</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      {current && (
        <Panel title={`Editing ${current}.yaml`}
               hint={dirty ? "unsaved changes" : "in sync with disk"}>
          <div className="body">
            <textarea
              value={yamlText}
              onChange={(e) => { setYamlText(e.target.value); setDirty(true); }}
              spellCheck={false}
              style={{ width: "100%", height: 420, fontFamily: "ui-monospace, Menlo, monospace",
                       fontSize: 12.5, border: "1px solid #dce2e8", borderRadius: 8,
                       padding: 12, lineHeight: 1.5, resize: "vertical" }} />
            <div style={{ display: "flex", gap: 10, marginTop: 12, alignItems: "center" }}>
              <button className="btn" onClick={doValidate} disabled={busy !== null}>Validate</button>
              <button className="btn primary" onClick={doSave} disabled={busy !== null}>
                Validate & Save
              </button>
              <button className="btn" onClick={doSelftest} disabled={busy !== null}>
                Run this pack's scenarios
              </button>
              <a className="btn" href="http://localhost:8090/talk" target="_blank" rel="noopener">
                Try it live ↗
              </a>
              {busy && <span style={{ color: "#8a96a3" }}>{busy}…</span>}
            </div>
            {messages.map((m, i) => (
              <p key={i} style={{ margin: "10px 0 0", fontSize: 13.5,
                  color: m.kind === "ok" ? "#0a6b5f" : m.kind === "bad" ? "#c0392b" : "#5b6875" }}>
                {m.kind === "ok" ? "✓ " : m.kind === "bad" ? "✗ " : ""}{m.text}
              </p>
            ))}
            {scenarioRows.length > 0 && (
              <table style={{ marginTop: 14 }}>
                <thead><tr><th>Scenario run</th><th>Result</th></tr></thead>
                <tbody>
                  {scenarioRows.map((r, i) => (
                    <tr key={i}>
                      <td style={{ fontFamily: "ui-monospace, monospace", fontSize: 12.5 }}>{r.line}</td>
                      <td>{r.passed
                        ? <span className="badge BOOKED">pass</span>
                        : <span className="badge HANDED_OFF">fail</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Panel>
      )}
    </Page>
  );
}
