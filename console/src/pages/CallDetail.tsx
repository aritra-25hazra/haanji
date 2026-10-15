import type { CSSProperties } from "react";
import { Link, useParams } from "react-router-dom";
import { engine, fmtMs, parseReceipts, parseTurns } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Chip, Empty, Icon, Loading, OutcomeChip, Page, Panel, Repair, Stamp, Tile, fmtDate, fmtTime, useData } from "../components/Common";
import type { CallRow } from "../types";

export default function CallDetail() {
  const { id = "" } = useParams();
  const { pack, online } = useApp();
  const { data, loading, error } = useData<CallRow | null>(
    () => (online ? engine.call(pack, id) : Promise.resolve(sample.call(id))), [pack, online, id]);

  if (loading && !data) return <Loading />;
  if (!data) {
    return (
      <Page title="Call">
        <Empty>Ye call nahi mili{error ? ` — ${error}` : ""}. <Link to="/calls">Calls pe wapas</Link></Empty>
      </Page>
    );
  }

  const turns = parseTurns(data.turns_json);
  const receipts = parseReceipts(data.receipts_json);
  const repairs = turns.reduce((n, t) => n + t.corrections.length, 0);

  return (
    <Page title="Call" sub={`${data.channel.toLowerCase()} · ${data.phone ?? "number nahi"} · ${fmtDate(data.started_at)} ${fmtTime(data.started_at)}`}
          actions={<Link className="btn btn-ghost btn-sm" to="/calls">Saari calls</Link>}>
      <div className="tiles">
        <Tile index={0} label="Outcome" value={<OutcomeChip outcome={data.outcome} />} />
        <Tile index={1} label="Shabd sudhaare" value={repairs} foot="tenant ki apni vocabulary se" />
        <Tile index={2} label="Receipt"
              value={receipts.length ? <Stamp><Icon name="lock" small />{receipts[receipts.length - 1]}</Stamp> : "—"}
              foot={receipts.length ? "signed aur chained" : "kuch likha nahi gaya"} />
      </div>

      <Panel title="Transcript" hint="jo suna gaya, aur agent ne kya padha aur bola">
        <div className="body transcript">
          {turns.length === 0 && <p className="muted">Is call ke turns record nahi hue.</p>}
          {turns.map((t, i) => (
            <div key={i} style={{ display: "contents" }}>
              <div className="bubble caller" data-reveal style={{ "--i": i * 2 } as CSSProperties}>
                {t.heard}
                {t.corrections.length > 0 && <div className="meta">{t.corrections.map((c, j) => <Repair key={j} c={c} />)}</div>}
              </div>
              <div className="bubble agent" data-reveal style={{ "--i": i * 2 + 1 } as CSSProperties}>
                {t.said}
                <div className="meta">
                  {t.tools.map((tool) => {
                    const hit = t.speculation_hits.includes(tool);
                    return <Chip key={tool} kind={hit ? "ok" : undefined}>{hit && <Icon name="bolt" small />}{tool}{hit ? " · speculated" : ""}</Chip>;
                  })}
                  {t.guard && <Chip kind="bad"><Icon name="shield" small />guardrail: {t.guard}</Chip>}
                  {t.interrupted && <Chip kind="muted">caller ne beech mein toka</Chip>}
                  <span className="mono muted" style={{ fontSize: 13 }}>{fmtMs(t.latency_ms)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      {receipts.length > 0 && (
        <Panel title="Pramaan receipts" hint="har ek Ed25519 signed, pichhli se chained"
               actions={<Link className="btn btn-ghost btn-sm" to="/ledger">Verify karo <Icon name="arrow" small /></Link>}>
          <div className="body row">
            {receipts.map((code) => <Stamp key={code}><Icon name="lock" small />RECEIPT {code}</Stamp>)}
          </div>
        </Panel>
      )}
    </Page>
  );
}
