import { api } from "../api";
import { Page, Panel, useData } from "../components/Common";

const DESCRIPTIONS: Record<string, string> = {
  dental_clinic: "Dental clinic — treatments, dentists, emergency escalation",
  salon_spa: "Salon and spa — stylists, long services, Monday closed",
  diagnostic_lab: "Diagnostic lab — fasting rules, home collection, no result interpretation",
  coaching_institute: "Coaching institute — demo classes, counsellors, no outcome promises",
};

export default function Packs() {
  const { data, loading, error } = useData(() => api.packs());
  if (loading) return <div className="empty">Loading…</div>;
  if (error || !data) return <div className="empty">Could not load: {error}</div>;

  return (
    <Page title="Vertical pack"
          sub="One file describes what your agent knows, what it refuses, and how it speaks.">
      <Panel title="Installed packs" hint={`${data.length} available`}>
        <table>
          <thead><tr><th>Pack</th><th>Covers</th><th /></tr></thead>
          <tbody>
            {data.map((p) => (
              <tr key={p}>
                <td><strong>{p.replace(/_/g, " ")}</strong></td>
                <td style={{ color: "#5b6875" }}>{DESCRIPTIONS[p] ?? "—"}</td>
                <td>{p === "dental_clinic"
                  ? <span className="badge BOOKED">in use</span>
                  : <a href="#switch">switch</a>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel title="What a pack contains">
        <div className="body">
          <dl className="kv">
            <dt>Catalogue</dt><dd>services, durations, prices, who performs each one</dd>
            <dt>Hours</dt><dd>working days, opening and closing times, breaks</dd>
            <dt>Persona</dt><dd>the greeting, the tone, how much the agent says at once</dd>
            <dt>Guardrails</dt>
            <dd>what the agent refuses outright, and what sends the call to a person</dd>
            <dt>Vocabulary</dt>
            <dd>seed words for the sound index — localities, brands, common phrases</dd>
            <dt>Knowledge</dt><dd>the questions callers actually ask, and your answers</dd>
            <dt>Scenarios</dt>
            <dd>the calls this pack must still handle correctly before it ships</dd>
          </dl>
        </div>
      </Panel>
    </Page>
  );
}
