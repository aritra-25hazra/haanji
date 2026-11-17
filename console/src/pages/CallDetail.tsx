import { useState, type CSSProperties } from "react";
import { Link, useParams } from "react-router-dom";
import { engine, fmtMs, parseReceipts, parseTurns } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { t, useT } from "../i18n";
import { Chip, DevToggle, Empty, Icon, Loading, NotLive, OutcomeChip, Page, Panel, Repair, Stamp, Tile, Waterfall, fmtDate, fmtTime, useData, useDevanagari } from "../components/Common";
import type { CallRow } from "../types";

export default function CallDetail() {
  const [showEngine, setShowEngine] = useState(false);
  const { id = "" } = useParams();
  const { pack, mode } = useApp();
  useT();
  const live = mode === "live";
  const loader = live ? () => engine.call(pack, id) : mode === "demo" ? () => Promise.resolve(sample.call(pack, id)) : null;
  const { data, loading, error } = useData<CallRow | null>(loader, [pack, mode, id]);
  // Hooks before any early return: the transliteration table follows the data.
  const dev = useDevanagari(data ? parseTurns(data.turns_json).flatMap((x) => [x.heard, x.said]) : []);

  if (!live && mode !== "demo") return <NotLive title={t("Call")} />;
  if (loading && !data) return <Loading />;
  if (!data) {
    return (
      <Page title={t("Call")}>
        <Empty>{t("Call not found")}{error ? `: ${error}` : ""}. <Link to="/calls">{t("Back to calls")}</Link></Empty>
      </Page>
    );
  }

  const turns = parseTurns(data.turns_json);
  const receipts = parseReceipts(data.receipts_json);
  const repairs = turns.reduce((n, x) => n + x.corrections.length, 0);

  return (
    <Page title={t("Call")} sub={`${data.channel.toLowerCase()} · ${data.phone ?? t("no number")} · ${fmtDate(data.started_at)} ${fmtTime(data.started_at)}`}
          actions={<><button className="btn btn-ghost btn-sm" aria-pressed={showEngine} onClick={() => setShowEngine((v) => !v)}>
                       {showEngine ? t("Hide engine details") : t("Engine details")}</button>
                     <DevToggle on={dev.on} toggle={dev.toggle} /><Link className="btn btn-ghost btn-sm" to="/calls">{t("All calls")}</Link></>}>
      <div className="tiles">
        <Tile index={0} label={t("Outcome")} value={<OutcomeChip outcome={data.outcome} />} />
        <Tile index={1} label={t("Misheard, then fixed")} value={repairs} foot={t("from your shop's own list")} />
        <Tile index={2} label={t("Receipt")}
              value={receipts.length ? <Stamp><Icon name="lock" small />{receipts[receipts.length - 1]}</Stamp> : "—"}
              foot={receipts.length ? t("signed and chained") : t("nothing was written")} />
      </div>

      <Panel title={t("Transcript")} hint={dev.on ? t("Devanagari is approximate: names and English words may be wrong") : t("what was heard, and what the agent read and said")}>
        <div className="body transcript">
          {turns.length === 0 && <p className="muted">{t("This call's turns were not recorded.")}</p>}
          {turns.map((turn, i) => (
            <div key={i} style={{ display: "contents" }}>
              <div className="bubble caller" data-reveal style={{ "--i": i * 2 } as CSSProperties}>
                {dev.map(turn.heard)}
                {turn.corrections.length > 0 && <div className="meta">{turn.corrections.map((c, j) => <Repair key={j} c={c} />)}</div>}
              </div>
              <div className="bubble agent" data-reveal style={{ "--i": i * 2 + 1 } as CSSProperties}>
                {dev.map(turn.said)}
                {/* the machinery of each reply is for the Engine details switch, not the owner's first read */}
                {showEngine && <div className="meta">
                  {turn.tools.map((tool) => {
                    const hit = turn.speculation_hits.includes(tool);
                    return <Chip key={tool} kind={hit ? "ok" : undefined}>{hit && <Icon name="bolt" small />}{tool}{hit ? " · speculated" : ""}</Chip>;
                  })}
                  {turn.guard && <Chip kind="bad"><Icon name="shield" small />guardrail: {turn.guard}</Chip>}
                  {turn.interrupted && <Chip kind="muted">{t("the caller cut in")}</Chip>}
                  <span className="mono muted" style={{ fontSize: 13 }}>{fmtMs(turn.latency_ms)}</span>
                </div>}
                {showEngine && turn.spans && turn.spans.length > 0 && <Waterfall spans={turn.spans} total={turn.latency_ms} />}
              </div>
            </div>
          ))}
        </div>
      </Panel>

      {receipts.length > 0 && (
        <Panel title={t("Pramaan receipts")} hint={t("each one Ed25519-signed, chained to the one before")}
               actions={<Link className="btn btn-ghost btn-sm" to="/ledger">{t("Verify")} <Icon name="arrow" small /></Link>}>
          <div className="body row">
            {receipts.map((code) => <Stamp key={code}><Icon name="lock" small />RECEIPT {code}</Stamp>)}
          </div>
        </Panel>
      )}
    </Page>
  );
}
