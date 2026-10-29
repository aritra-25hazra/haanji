import type { CSSProperties } from "react";
import { engine } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Chip, Empty, Loading, NotLive, Page, Panel, Register, useData } from "../components/Common";

const SUB = "Ek file batati hai agent kya jaanta hai, kya mana karta hai, aur kaise bolta hai.";

export default function Packs() {
  const { pack, mode, setPack } = useApp();
  const live = mode === "live";
  const loader = live ? () => engine.packs().then((r) => r.packs) : mode === "demo" ? () => Promise.resolve(sample.packs()) : null;
  const { data, loading, error, reload } = useData(loader, [mode]);

  if (!live && mode !== "demo") return <NotLive title="Vertical packs" sub={SUB} />;
  if (loading && !data) return <Loading />;
  if (!data) {
    return (
      <Page title="Packs">
        <Empty>Load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty>
      </Page>
    );
  }

  return (
    <Page title="Vertical packs" sub={SUB}>
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

      <Panel title="Ek pack mein kya hota hai">
        <div className="body">
          <dl style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: "8px 16px", margin: 0 }}>
            <dt className="muted">Catalogue</dt><dd style={{ margin: 0 }}>services, kitna time, daam, kaun karta hai</dd>
            <dt className="muted">Hours</dt><dd style={{ margin: 0 }}>din, khulne-band hone ka time, breaks</dd>
            <dt className="muted">Persona</dt><dd style={{ margin: 0 }}>greeting, tone, ek baar mein kitna bolna</dd>
            <dt className="muted">Guardrails</dt><dd style={{ margin: 0 }}>kya seedha mana karna, kya insaan ko dena</dd>
            <dt className="muted">Vocabulary</dt><dd style={{ margin: 0 }}>sound-index ke seed shabd — ilaake, brands, aam phrases</dd>
            <dt className="muted">Knowledge</dt><dd style={{ margin: 0 }}>jo sawaal log sach mein poochte hain, aur jawab</dd>
            <dt className="muted">Scenarios</dt><dd style={{ margin: 0 }}>wo calls jo pack ko ship hone se pehle paas karni hain</dd>
          </dl>
        </div>
      </Panel>
    </Page>
  );
}
