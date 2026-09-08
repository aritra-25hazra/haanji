import { useParams } from "react-router-dom";
import { api } from "../api";
import { Badge, Page, Panel, fmtDuration, useData } from "../components/Common";
import { live } from "../live";
import type { ConversationDetail, Turn } from "../types";

async function loadDetail(id: string): Promise<ConversationDetail> {
  if (!id.startsWith("live-")) return api.conversation(id);
  const status = await live.status();
  const row = status ? await live.call(status.default_pack, id.slice(5)) : null;
  if (!row) throw new Error("live call not found — is the engine server running?");
  const turns = JSON.parse(row.turns_json) as {
    seq: number; heard: string; corrected: string; said: string;
    tools: string[]; speculation_hits: string[]; guard: string;
    latency_ms: number | null; interrupted: boolean;
    corrections: { from_token: string; to_surface: string; asr_confidence: number;
                   ngram: number }[];
  }[];
  const flat: Turn[] = [];
  let seq = 0;
  for (const t of turns) {
    flat.push({ seq: ++seq, speaker: "caller", text: t.corrected, raw_text: t.heard,
      corrections: t.corrections, tool_calls: t.tools, speculation_hits: t.speculation_hits,
      latency_ms: t.latency_ms, interrupted: t.interrupted });
    flat.push({ seq: ++seq, speaker: "agent", text: t.said, raw_text: null, corrections: [],
      tool_calls: [], latency_ms: null, interrupted: false });
  }
  return {
    conversation_id: row.call_id, channel: row.channel as ConversationDetail["channel"],
    caller_phone: row.phone ?? "—", started_at: row.started_at, ended_at: null,
    outcome: row.outcome as ConversationDetail["outcome"], duration_ms: 0,
    turns: flat,
    receipts: (JSON.parse(row.receipts_json) as string[]).map((code, i) => ({
      seq: i + 1, short_code: code, action: "book_appointment", action_args: {},
      confirmation: {}, transcript_excerpt: "", occurred_at: row.started_at, chain_hash: "",
    })),
  };
}

function TurnRow({ turn }: { turn: Turn }) {
  return (
    <div className={`turn ${turn.speaker}`}>
      <div className="who">{turn.speaker}</div>
      <div>
        <div className="text">{turn.text}</div>
        {turn.corrections.map((c, i) => (
          <div className="repair" key={i}>
            heard <s>{c.from_token}</s> at {(c.asr_confidence * 100).toFixed(0)}% confidence
            {" · "}read as <b>{c.to_surface}</b>
          </div>
        ))}
        {(turn.tool_calls.length > 0 || turn.latency_ms || turn.interrupted) && (
          <div className="meta">
            {turn.tool_calls.map((t) => (
              <span key={t}>
                {t}
                {turn.speculation_hits?.includes(t) && " · answered from a speculation"}
              </span>
            ))}
            {turn.latency_ms != null && <span>{turn.latency_ms} ms</span>}
            {turn.interrupted && <span>caller interrupted</span>}
          </div>
        )}
      </div>
    </div>
  );
}

export default function CallDetail() {
  const { id = "" } = useParams();
  const { data, loading, error } = useData(() => loadDetail(id), [id]);
  if (loading) return <div className="empty">Loading…</div>;
  if (error || !data) return <div className="empty">Could not load: {error}</div>;

  const receipt = data.receipts[0];

  return (
    <Page title="Call" sub={`${data.channel.toLowerCase()} · ${data.caller_phone} · ${fmtDuration(data.duration_ms)}`}>
      <div className="cards">
        <div className="card">
          <h3>Outcome</h3>
          <div className="value" style={{ fontSize: 20 }}><Badge kind={data.outcome} /></div>
        </div>
        <div className="card">
          <h3>Words repaired</h3>
          <div className="value">
            {data.turns.reduce((n, t) => n + t.corrections.length, 0)}
          </div>
          <div className="foot">by the tenant's own vocabulary</div>
        </div>
        <div className="card">
          <h3>Receipt</h3>
          <div className="value" style={{ fontSize: 20 }}>
            {receipt ? <span className="badge mono">{receipt.short_code}</span> : "—"}
          </div>
          <div className="foot">{receipt ? "signed and chained" : "nothing was written"}</div>
        </div>
      </div>

      <Panel title="Transcript" hint="what the recogniser heard, and what the agent read">
        <div className="body" style={{ paddingTop: 4, paddingBottom: 4 }}>
          {data.turns.map((t) => <TurnRow key={t.seq} turn={t} />)}
        </div>
      </Panel>

      {receipt && receipt.confirmation.prompt_text && (
        <Panel title="Pramaan receipt"
               hint="the words that authorised the write, sealed with them">
          <div className="body">
            <dl className="kv">
              <dt>Action</dt><dd>{receipt.action}</dd>
              <dt>The agent asked</dt><dd>“{receipt.confirmation.prompt_text}”</dd>
              <dt>The caller replied</dt><dd>“{receipt.confirmation.reply_text}”</dd>
              <dt>Recognised at</dt>
              <dd>{((receipt.confirmation.asr_confidence ?? 0) * 100).toFixed(1)}% confidence,
                  {" "}{receipt.confirmation.audio_offset_ms} ms after the question ended</dd>
              <dt>Sealed at</dt><dd>{new Date(receipt.occurred_at).toLocaleString("en-IN")}</dd>
              <dt>Chain hash</dt><dd className="mono">{receipt.chain_hash}</dd>
            </dl>
          </div>
        </Panel>
      )}
    </Page>
  );
}
