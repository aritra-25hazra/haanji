import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Badge, Page, Panel, fmtDuration, fmtTime, useData } from "../components/Common";
import { live, type LiveCallRow } from "../live";

export default function Calls() {
  const { data, loading, error } = useData(() => api.conversations());
  const [rows, setRows] = useState<LiveCallRow[] | null>(null);
  useEffect(() => {
    live.status().then((s) => s && live.calls(s.default_pack)
      .then((r) => setRows(r ? r.conversations : null)));
  }, []);
  if (loading) return <div className="empty">Loading…</div>;
  if (error || !data) return <div className="empty">Could not load: {error}</div>;

  return (
    <Page title="Calls" sub="Newest first. Open a call to read the transcript and its receipt.">
      {rows && rows.length > 0 && (
        <Panel title="Live calls — this machine" hint={`${rows.length} recorded by the engine server`}>
          <table>
            <thead>
              <tr><th>Time</th><th>Channel</th><th>Caller</th><th>Outcome</th>
                  <th>Repairs</th><th>Spec hits</th><th /></tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.call_id}>
                  <td>{c.started_at.slice(11, 16)}</td>
                  <td>{c.channel.toLowerCase()}</td>
                  <td className="mono">{c.phone ?? "—"}</td>
                  <td><Badge kind={c.outcome} /></td>
                  <td>{c.corrections}</td>
                  <td>{c.spec_hits}</td>
                  <td><Link to={`/calls/live-${c.call_id}`}>open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
      <Panel title={rows && rows.length ? "Sample dataset" : "Recent conversations"}
             hint={`${data.length} shown`}>
        <table>
          <thead>
            <tr>
              <th>Time</th><th>Channel</th><th>Caller</th>
              <th>Outcome</th><th>Length</th><th />
            </tr>
          </thead>
          <tbody>
            {data.map((c) => (
              <tr key={c.conversation_id}>
                <td>{fmtTime(c.started_at)}</td>
                <td>{c.channel.toLowerCase()}</td>
                <td className="mono">{c.caller_phone}</td>
                <td><Badge kind={c.outcome} /></td>
                <td>{fmtDuration(c.duration_ms)}</td>
                <td><Link to={`/calls/${c.conversation_id}`}>open</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </Page>
  );
}
