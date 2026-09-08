import { api } from "../api";
import { Page, Panel, Stat, useData } from "../components/Common";

export default function Ledger() {
  const { data, loading, error } = useData(() => api.receiptsVerify());
  if (loading) return <div className="empty">Verifying…</div>;
  if (error || !data) return <div className="empty">Could not verify: {error}</div>;

  return (
    <Page title="Pramaan ledger"
          sub="Every booking and cancellation this agent made, sealed against the words that authorised it.">
      <div className="cards">
        <Stat label="Receipts in the chain" value={data.checked.toLocaleString("en-IN")} />
        <Stat label="Chain state"
              value={
                <span className="verify">
                  <span className={`dot ${data.ok ? "ok" : "bad"}`} />
                  {data.ok ? "intact" : `broken at ${data.first_broken_seq}`}
                </span>}
              foot={data.ok ? "every hash and signature re-derived just now" : data.reason ?? ""} />
        <Stat label="Unconfirmed writes" value="0"
              foot="the ledger refuses to seal one" />
      </div>

      <Panel title="Verify this yourself"
             hint="the check does not depend on anything Haanji says">
        <div className="body">
          <p style={{ marginTop: 0 }}>
            Download the export and run the open-source verifier. It re-computes every
            payload hash, re-links the chain, and checks each Ed25519 signature against
            the public key below. Nothing in the export has to be trusted — a single
            edited character anywhere in any receipt changes its hash, and every receipt
            after it too.
          </p>
          <dl className="kv">
            <dt>Public key (Ed25519)</dt><dd className="mono">{data.public_key}</dd>
            <dt>Export</dt><dd><a href="/api/v1/receipts/export">receipts.json</a></dd>
            <dt>Verifier</dt>
            <dd className="mono">python -m haanji.cli verify --db ledger.db --tenant &lt;id&gt;</dd>
          </dl>
        </div>
      </Panel>
    </Page>
  );
}
