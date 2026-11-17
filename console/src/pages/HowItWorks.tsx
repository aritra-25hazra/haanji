import { useState } from "react";
import PACKS from "../packs.json";
import { Chip, Empty, Page, Panel, Register } from "../components/Common";
import { engine } from "../engine";
import { en, t, useT } from "../i18n";
import { businessName } from "../labels";
import { MEASURED, measuredOn, ms, pct } from "../results";
import { useApp } from "../state";

const SETUP: Record<string, string> = {
  full: en("Everything on"), no_speculation: en("Without early lookups"), no_bhasha: en("Without Bhasha"), baseline: en("Neither (plain baseline)"),
};
const SCENARIOS = new Map((PACKS as { packs: { pack_id: string; scenarios: number }[] }).packs.map((p) => [p.pack_id, p.scenarios]));

/** What happens on a call, step by step, and what the benchmark measured —
 *  every number read from the benchmark's own results file. */
export default function HowItWorks() {
  useT();
  const { mode, pack, isOwner } = useApp();
  const h = MEASURED.headline, led = MEASURED.ledger;
  const steps = [
    [t("The caller speaks"), t("On the phone, on WhatsApp or on the web page. HaanJi greets them and says it is an AI assistant.")],
    [t("Bhasha repairs the words"), t("Speech recognisers mishear Indian shop words (\"root canal\" becomes \"route canal\"). Bhasha checks the shop's own list of services, names and times, and fixes a word only when it is sure.")],
    [t("The agent asks one thing at a time"), t("Service, day and time, name, number. It says when a time is free before asking for details, and passes the call to staff for an emergency or a complaint.")],
    [t("Lookups start early"), t("While the caller is still talking, read-only lookups such as free slots start in the background. The answer is used only if the final question asks for exactly the same thing; a booking is never started early.")],
    [t("Confirm, then write"), t("The agent reads the booking back, with the last digits of the number. Only after a yes is it written, and the booking and the yes are sealed into a Pramaan receipt that shows any later edit.")],
    [t("The owner sees it"), t("The booking is on the calendar, the customer gets a WhatsApp reminder, and the owner gets an evening summary.")],
  ];
  const rows: [string, string, string, string?][] = [
    [t("Misheard names, services, times"), pct(h.entity_error_rate_without_bhasha!), pct(h.entity_error_rate_with_bhasha!, 2), t("at {noise} recogniser errors", { noise: pct(h.noise_rate!, 0) })],
    [t("Corrections that made a word worse"), "—", String(h.harmful_corrections_transcript), t("of {n} words checked", { n: h.entities_scored!.toLocaleString("en-IN") })],
    [t("Calls that end the way they should"), pct(h.task_success_without_bhasha!), pct(h.task_success_with_bhasha!), t("noisy calls")],
    [t("Median reply, read questions"), ms(h.read_turn_p50_without_speculation!), ms(h.read_turn_p50_with_speculation!), t("{p}% of early lookups were used", { p: Math.round(h.speculation_hit_rate! * 100) })],
    [t("Slow replies (p90), read questions"), ms(h.read_turn_p90_without_speculation!), ms(h.read_turn_p90_with_speculation!)],
    [t("Slow replies (p90), booking turns"), ms(h.write_turn_p90_without_speculation!), ms(h.write_turn_p90_with_speculation!), t("slightly slower; reported, not hidden")],
    [t("Edited receipts caught"), "—", `${led.mutations_detected} / ${led.mutations_attempted}`, t("chain of {n} receipts", { n: led.chain_length })],
    [t("Bookings written without the caller's yes"), "—", String(led.unconfirmed_writes_accepted)],
  ];
  return (
    <Page title={t("How it works")} sub={t("One call, from the first word to the signed receipt, and what was measured.")}>
      <ol className="how-steps">
        {steps.map(([title, text], i) => <li key={i}><b>{title}</b><span>{text}</span></li>)}
      </ol>

      <Panel title={t("What the benchmark measured")} hint={t("measured on {date}", { date: measuredOn() })}>
        <Register head={<><th>{t("Measure")}</th><th className="right">{t("Without")}</th><th className="right">{t("With HaanJi")}</th><th>{t("Note")}</th></>}>
          {rows.map(([name, a, b, note]) => (
            <tr key={name}><td>{name}</td><td className="num right">{a}</td><td className="num right"><strong>{b}</strong></td><td className="muted">{note ?? ""}</td></tr>
          ))}
        </Register>
        <p className="body muted small">
          {t("{scenarios} scripted calls across {packs} shops, {reps} runs each, with recogniser errors added on purpose. Simulated calls, not live customers. To reproduce:", { scenarios: MEASURED.scenarios, packs: MEASURED.packs, reps: MEASURED.reps })}{" "}
          <code>{MEASURED.how_to_reproduce}</code>
        </p>
      </Panel>

      <Panel title={t("More noise, same repair")} hint={t("{n} sentences at each level", { n: MEASURED.noise[0]?.sentences.toLocaleString("en-IN") ?? "0" })}>
        <Register head={<><th>{t("Recogniser errors")}</th><th className="right">{t("Misheard, without Bhasha")}</th><th className="right">{t("With Bhasha")}</th></>}>
          {MEASURED.noise.map((n) => (
            <tr key={n.noise}><td className="num">{pct(n.noise, 0)}</td><td className="num right">{pct(n.error_without)}</td><td className="num right"><strong>{pct(n.error_with, 2)}</strong></td></tr>
          ))}
        </Register>
      </Panel>

      <Panel title={t("Each part switched off")} hint={t("scripted calls, no added noise")}>
        <Register head={<><th>{t("Setup")}</th><th className="right">{t("Calls")}</th><th className="right">{t("Right outcome")}</th><th className="right">{t("Writes without a yes")}</th></>}>
          {Object.entries(MEASURED.configs).map(([name, c]) => (
            <tr key={name}><td>{SETUP[name] ? t(SETUP[name]) : name}</td><td className="num right">{c.calls}</td><td className="num right">{pct(c.outcome_accuracy)}</td><td className="num right">{c.unconfirmed_writes}</td></tr>
          ))}
        </Register>
      </Panel>

      <RunScenarios live={mode === "live"} allowed={isOwner} pack={pack} />
    </Page>
  );
}

function RunScenarios({ live, allowed, pack }: { live: boolean; allowed: boolean; pack: string }) {
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState<{ ok: boolean; results: { passed: boolean; line: string }[]; summary: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const n = SCENARIOS.get(pack);
  async function run() {
    setBusy(true); setError(null);
    try { setOut(await engine.selftest(pack)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <Panel title={t("Run the scenarios yourself")} hint={businessName(pack)}
           actions={<button className="btn btn-primary btn-sm" onClick={run} disabled={!live || !allowed || busy}>
             {busy ? t("Running…") : n ? t("Run {n} scenarios", { n }) : t("Run the scenarios")}</button>}>
      {!live ? <Empty><p>{t("This runs on the live engine. Switch Sample off once the engine is awake.")}</p></Empty>
        : !allowed ? <Empty><p>{t("Only the owner can run the scenarios.")}</p></Empty>
        : error ? <Empty><p>{error}</p></Empty>
        : out ? (
          <div className="body">
            <p><Chip kind={out.ok ? "ok" : "bad"}>{out.ok ? t("All passed") : t("Some failed")}</Chip> {out.summary}</p>
            <ul className="scenario-list">{out.results.map((r, i) => <li key={i} className={r.passed ? "ok" : "bad"}><span aria-hidden="true">{r.passed ? "✓" : "✗"}</span> {r.line}</li>)}</ul>
          </div>
        ) : <Empty><p>{t("Each scenario is a scripted call with the outcome it must reach. The engine plays them against this shop now.")}</p></Empty>}
    </Panel>
  );
}
