import { useCallback, useState, type CSSProperties } from "react";
import DecryptedText from "../components/DecryptedText";
import { engine, tamper, verifyExport } from "../engine";
import { sample } from "../sample";
import { en, t, useT } from "../i18n";
import { useApp } from "../state";
import { Chip, Empty, Icon, Loading, NotLive, Page, Panel, Register, Stamp, Tile, useData } from "../components/Common";
import type { Export, Verdict } from "../types";

const SUB = en("Every booking is a signed, chained receipt. This page checks it again in your browser, without trusting the server.");

export default function Ledger() {
  const { pack, mode } = useApp();
  useT();
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [runs, setRuns] = useState(0);              // each verification re-draws the codes

  const run = useCallback(async (exp: Export, note: string) => {
    setBusy(true); setProblem(null);
    try { setVerdict(await verifyExport(exp)); setLabel(note); setRuns((n) => n + 1); }
    catch (e) { setProblem((e as Error).message); }
    finally { setBusy(false); }
  }, []);

  const live = mode === "live";
  const loader = live
    ? async () => { const exp = await engine.export(pack); await run(exp, t("on the engine's export, just now")); return exp; }
    : mode === "demo" ? () => Promise.resolve(sample.export(pack)) : null;
  const { data, loading, error, reload } = useData<Export>(loader, [pack, mode]);
  // The real counter: writes the ledger refused for lacking a confirmation proof.
  const ops = useData(live ? () => engine.ops(pack) : null, [pack, mode]);

  if (!live && mode !== "demo") return <NotLive title="Pramaan ledger" sub={t(SUB)} />;
  if (loading && !data) return <Loading kind="table" />;
  if (!data) {
    return (
      <Page title="Pramaan">
        <Empty>{t("The export did not load: {error}", { error: error ?? "" })}<button className="btn btn-ghost btn-sm" onClick={reload}>{t("Try again")}</button></Empty>
      </Page>
    );
  }

  const shown = live ? verdict : null;         // a sample export is never "verified"
  const firstBroken = shown && !shown.ok ? shown.firstBrokenSeq : null;
  const rows = shown
    ? shown.rows
    : data.receipts.map((r) => ({ seq: r.seq, action: r.action, code: String(r.short_code ?? ""), ok: null as boolean | null, reason: null as string | null }));
  const refused = ops.data?.counters.unconfirmed_refused;

  return (
    <Page title="Pramaan ledger" sub={t(SUB)}
          actions={live ? (
            <>
              <button className="btn btn-ghost btn-sm" disabled={busy} onClick={reload}><Icon name="refresh" small />{t("Verify again")}</button>
              <button className="btn btn-danger btn-sm" disabled={busy || !data.receipts.length}
                      onClick={() => { const tp = tamper(data); void run(tp.edited, t("after editing receipt seq {seq} right here", { seq: tp.seq })); }}>
                <Icon name="x" small />{t("Tamper with one field and check again")}
              </button>
            </>
          ) : undefined}>
      <div className="tiles">
        <Tile index={0} label="Receipts" value={data.receipts.length} foot={`tenant ${data.tenant_id}`} />
        <Tile index={1} label="Chain"
              value={shown
                ? (shown.ok ? <Stamp tone="leaf"><Icon name="check" small />VALID</Stamp> : <Stamp><Icon name="x" small />BROKEN</Stamp>)
                : <span className="muted" style={{ fontSize: 16 }}>{live ? t("checking…") : t("needs the live engine")}</span>}
              foot={shown
                ? (shown.ok ? t("{n} receipts, every hash and signature rebuilt", { n: shown.checked }) : `seq ${shown.firstBrokenSeq}: ${shown.reason}`)
                : (live ? "" : t("sample receipts cannot be verified"))} />
        <Tile index={2} label={t("Writes without a confirmation")}
              value={refused ?? "—"}
              foot={refused == null
                ? (live ? (ops.error ? t("counter not found: {error}", { error: ops.error }) : t("coming from the engine…")) : t("a counter from the live engine"))
                : t("writes the ledger refused for lacking proof · engine counter")} />
      </div>

      {problem && <div className="banner" role="status"><Icon name="x" small />{t("Could not verify: {problem}", { problem })}</div>}

      {shown && (
        <Panel title="Verdict" hint={label}>
          <div className="body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              {shown.ok
                ? <Stamp tone="leaf" big><Icon name="check" />VALID · {shown.checked} receipts · chain intact</Stamp>
                : <Stamp big><Icon name="x" />BROKEN at seq {shown.firstBrokenSeq} · {shown.reason}</Stamp>}
            </div>
            <div className="chain" aria-hidden="true">
              {rows.map((r) => <i key={r.seq} className={firstBroken != null && r.seq >= firstBroken ? "bad" : undefined} />)}
              <i className="next" />
            </div>
            <div className="mono muted" style={{ fontSize: 12, wordBreak: "break-all" }}>public key (Ed25519): {data.public_key || "—"}</div>
            <p className="muted" style={{ fontSize: 13 }}>{t("The \"tamper\" button changes only your browser's copy; nothing is sent to the server.")}</p>
          </div>
        </Panel>
      )}

      <Panel title="Receipts" hint={rows.length ? `${rows.length} entries` : t("none yet")}>
        {rows.length === 0 ? (
          <Empty>
            <p>{t("The export has no receipts.")}</p>
            <a className="btn btn-primary" href="/engine/talk" target="_blank" rel="noopener noreferrer">{t("Make a booking first")} <Icon name="external" small /></a>
          </Empty>
        ) : (
          <Register head={<><th>Seq</th><th>Action</th><th>Code</th><th>Verdict</th><th>Reason</th></>}>
            {rows.map((r, i) => (
              <tr key={r.seq} data-reveal style={{ "--i": i } as CSSProperties}>
                <td className="num">{r.seq}</td>
                <td>{r.action}</td>
                <td className="mono">{r.code
                  // The code's own characters settle into place each time the browser re-derives the chain.
                  ? <DecryptedText key={`${runs}-${r.code}`} text={`${r.code.slice(0, 4)}-${r.code.slice(4, 8)}`} animateOn="view"
                                   sequential revealDirection="start" useOriginalCharsOnly speed={40} />
                  : "—"}</td>
                <td>
                  {r.ok === true ? <Chip kind="ok"><Icon name="check" small />verified</Chip>
                    : r.ok === false ? <Chip kind="bad"><Icon name="x" small />BROKEN</Chip>
                    : <Chip kind="muted">{live ? "skipped" : "sample"}</Chip>}
                </td>
                <td className="muted">{r.reason ?? (r.ok === true ? t("hash + link + signature, all three rebuilt") : "")}</td>
              </tr>
            ))}
          </Register>
        )}
      </Panel>
    </Page>
  );
}
