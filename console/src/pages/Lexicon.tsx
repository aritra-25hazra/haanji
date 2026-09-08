import { api } from "../api";
import { Page, Panel, useData } from "../components/Common";

export default function Lexicon() {
  const { data, loading, error } = useData(() => api.lexicon());
  if (loading) return <div className="empty">Loading…</div>;
  if (error || !data) return <div className="empty">Could not load: {error}</div>;

  const total = data.reduce((n, e) => n + e.repairs_30d, 0);

  return (
    <Page title="Bhasha lexicon"
          sub="The words this business uses, indexed by how they sound. Built from your catalogue — you never type this list.">
      <Panel title="Vocabulary"
             hint={`${data.length} entries · ${total} repairs in the last 30 days`}>
        <table>
          <thead>
            <tr>
              <th>Word</th><th>Kind</th><th>Also heard as</th>
              <th>Sound key</th><th>Weight</th><th>Repairs (30d)</th>
            </tr>
          </thead>
          <tbody>
            {data.map((e) => (
              <tr key={e.surface}>
                <td><strong>{e.surface}</strong></td>
                <td>{e.entry_type.toLowerCase()}</td>
                <td style={{ color: "#5b6875" }}>{e.variants.join(", ") || "—"}</td>
                <td className="mono">{e.phonetic_key}</td>
                <td>{e.weight.toFixed(2)}</td>
                <td>{e.repairs_30d}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel title="How a repair is decided">
        <div className="body">
          <p style={{ marginTop: 0 }}>
            A word is only replaced when two independent things are true at once: the
            recogniser was <strong>not confident</strong> about it, and it lands on
            <strong> exactly the same sound key</strong> as something in this list, within
            a small spelling distance. Either test on its own produces false corrections,
            and a layer that damages good transcripts is worse than no layer at all.
          </p>
          <p style={{ marginBottom: 0, color: "#5b6875" }}>
            Names the caller has just introduced are never corrected, whatever they sound
            like.
          </p>
        </div>
      </Panel>
    </Page>
  );
}
