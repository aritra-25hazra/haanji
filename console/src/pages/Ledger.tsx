import { useCallback, useState, type CSSProperties } from "react";
import { engine, tamper, verifyExport } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { Chip, Empty, Icon, Loading, Page, Panel, Register, Stamp, Tile, useData } from "../components/Common";
import type { Export, Verdict } from "../types";

export default function Ledger() {
  const { pack, online } = useApp();
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const run = useCallback(async (exp: Export, note: string) => {
    setBusy(true); setProblem(null);
    try { setVerdict(await verifyExport(exp)); setLabel(note); }
    catch (e) { setProblem((e as Error).message); }
    finally { setBusy(false); }
  }, []);

  const { data, loading, error, reload } = useData<Export>(async () => {
    if (!online) { setVerdict(null); return sample.export(); }
    const exp = await engine.export(pack);
    await run(exp, "engine ke export pe, abhi");
    return exp;
  }, [pack, online]);

  if (loading && !data) return <Loading />;
  if (!data) {
    return (
      <Page title="Pramaan">
        <Empty>Export load nahi hua: {error}<button className="btn btn-ghost btn-sm" onClick={reload}>Dobara try karo</button></Empty>
      </Page>
    );
  }

  const firstBroken = verdict && !verdict.ok ? verdict.firstBrokenSeq : null;
  const rows = verdict
    ? verdict.rows
    : data.receipts.map((r) => ({ seq: r.seq, action: r.action, code: String(r.short_code ?? ""), ok: null as boolean | null, reason: null as string | null }));

  return (
    <Page title="Pramaan ledger"
          sub="Har booking ek signed, chained receipt — aur ye page usse aapke browser mein dobara jaanchta hai, server pe bharosa kiye bina."
          actions={online ? (
            <>
              <button className="btn btn-ghost btn-sm" disabled={busy} onClick={reload}><Icon name="refresh" small />Dobara verify karo</button>
              <button className="btn btn-danger btn-sm" disabled={busy || !data.receipts.length}
                      onClick={() => { const t = tamper(data); void run(t.edited, `receipt seq ${t.seq} ko yahin edit karne ke baad`); }}>
                <Icon name="x" small />Ek field chhedo aur dobara check karo
              </button>
            </>
          ) : undefined}>
      <div className="tiles">
        <Tile index={0} label="Receipts" value={data.receipts.length} foot={`tenant ${data.tenant_id}`} />
        <Tile index={1} label="Chain"
              value={verdict
                ? (verdict.ok ? <Stamp tone="leaf"><Icon name="check" small />VALID</Stamp> : <Stamp><Icon name="x" small />BROKEN</Stamp>)
                : <span className="muted" style={{ fontSize: 16 }}>{online ? "jaanch raha hoon…" : "live engine chahiye"}</span>}
              foot={verdict
                ? (verdict.ok ? `${verdict.checked} receipts, har hash aur signature dobara bana` : `seq ${verdict.firstBrokenSeq}: ${verdict.reason}`)
                : (online ? "" : "sample receipts verify nahi ho sakte")} />
        <Tile index={2} label="Bina confirm writes" value={0} foot="ledger inhe accept hi nahi karta" />
      </div>

      {problem && <div className="banner" role="status"><Icon name="x" small />Verify nahi ho paya: {problem}</div>}

      {verdict && (
        <Panel title="Verdict" hint={label}>
          <div className="body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              {verdict.ok
                ? <Stamp tone="leaf" big><Icon name="check" />VALID · {verdict.checked} receipts · chain intact</Stamp>
                : <Stamp big><Icon name="x" />BROKEN at seq {verdict.firstBrokenSeq} · {verdict.reason}</Stamp>}
            </div>
            <div className="chain" aria-hidden="true">
              {rows.map((r) => <i key={r.seq} className={firstBroken != null && r.seq >= firstBroken ? "bad" : undefined} />)}
              <i className="next" />
            </div>
            <div className="mono muted" style={{ fontSize: 12, wordBreak: "break-all" }}>public key (Ed25519): {data.public_key || "—"}</div>
            <p className="muted" style={{ fontSize: 13 }}>"Chhedo" wala button sirf aapke browser ki copy badalta hai — server pe kuch nahi jaata.</p>
          </div>
        </Panel>
      )}

      <Panel title="Receipts" hint={rows.length ? `${rows.length} entries` : "abhi koi nahi"}>
        {rows.length === 0 ? (
          <Empty>
            <p>Export mein koi receipt nahi.</p>
            <a className="btn btn-primary" href="/engine/talk" target="_blank" rel="noopener noreferrer">Pehle ek booking karo <Icon name="external" small /></a>
          </Empty>
        ) : (
          <Register head={<><th>Seq</th><th>Action</th><th>Code</th><th>Verdict</th><th>Reason</th></>}>
            {rows.map((r, i) => (
              <tr key={r.seq} data-reveal style={{ "--i": i } as CSSProperties}>
                <td className="num">{r.seq}</td>
                <td>{r.action}</td>
                <td className="mono">{r.code ? `${r.code.slice(0, 4)}-${r.code.slice(4, 8)}` : "—"}</td>
                <td>
                  {r.ok === true ? <Chip kind="ok"><Icon name="check" small />verified</Chip>
                    : r.ok === false ? <Chip kind="bad"><Icon name="x" small />BROKEN</Chip>
                    : <Chip kind="muted">{online ? "skipped" : "sample"}</Chip>}
                </td>
                <td className="muted">{r.reason ?? (r.ok === true ? "hash + link + signature, teeno dobara bane" : "")}</td>
              </tr>
            ))}
          </Register>
        )}
      </Panel>
    </Page>
  );
}
