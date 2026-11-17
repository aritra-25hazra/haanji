import { useMemo, useState } from "react";
import { engine } from "../engine";
import Stepper, { Step } from "../components/Stepper";
import { en, t, useT } from "../i18n";
import { useApp } from "../state";
import { Chip, Icon, NotLive, Page, Panel } from "../components/Common";
import type { Draft, DraftRequest } from "../types";

const TYPES: [string, string][] = [["clinic", "Clinic / doctor"], ["salon", "Salon / spa"], ["lab", "Diagnostic lab"], ["coaching", "Coaching institute"], ["other", en("Something else")]];
const DAYS: [string, string][] = [["mon", en("Mon")], ["tue", en("Tue")], ["wed", en("Wed")], ["thu", en("Thu")], ["fri", en("Fri")], ["sat", en("Sat")], ["sun", en("Sun")]];
const STEPS = [en("Shop"), en("People"), en("Hours"), "Services", en("Ready")];

interface DayHours { open: boolean; from: string; to: string }
interface ServiceRow { name: string; duration: string; price: string; staff: string[]; aliases: string }

const splitList = (s: string) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);

/** Sample mode: the pack the engine would draft, made in the browser so the
 *  five steps can be walked end to end. Nothing is saved anywhere. */
function previewDraft(r: DraftRequest): Draft {
  const problems: string[] = [];
  if (!r.business_name) problems.push("Business name is missing (step 1).");
  if (!r.staff.length) problems.push("Add at least one person (step 2).");
  if (!r.services.length) problems.push("Add at least one service (step 4).");
  const id = r.business_name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "new_shop";
  const yaml = [
    `pack: ${id}`, `display_name: ${r.business_name || "New shop"}`, `language: ${r.language}`,
    "persona:", `  agent_name: ${r.agent_name}`, `  business_name: ${r.business_name}`,
    `  greeting: "${r.greeting ?? `Haanji, ${r.business_name}. Main aapki kya madad karun?`}"`,
    `staff: [${r.staff.join(", ")}]`, "hours:",
    ...Object.entries(r.hours).map(([d, h]) => `  ${d}: ${h ? `["${h[0]}", "${h[1]}"]` : "null"}`),
    "services:",
    ...r.services.flatMap((s) => [`  - name: ${s.name}`, `    duration_min: ${s.duration_min}`, `    price_inr: ${s.price_inr ?? "null"}`,
                                  `    staff: [${s.staff.join(", ")}]`, `    aliases: [${s.aliases.join(", ")}]`]),
  ].join("\n");
  return { pack_id: id, yaml, problems, exists: false } as Draft;
}

export default function Onboard() {
  const { mode, isOwner, status, setPack, refresh } = useApp();
  useT();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [type, setType] = useState("clinic");
  const [language, setLanguage] = useState("hinglish");
  const [agent, setAgent] = useState("Haanji");
  const [greeting, setGreeting] = useState("");
  const [role, setRole] = useState("");
  const [staffText, setStaffText] = useState("");
  const [hours, setHours] = useState<Record<string, DayHours>>(() =>
    Object.fromEntries(DAYS.map(([d]) => [d, { open: d !== "sun", from: "10:00", to: "20:00" }])));
  const [services, setServices] = useState<ServiceRow[]>([{ name: "", duration: "30", price: "", staff: [], aliases: "" }]);
  const [placesText, setPlacesText] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState<{ kind: "ok" | "bad"; text: string }[]>([]);
  const [results, setResults] = useState<{ passed: boolean; line: string }[]>([]);
  const [saved, setSaved] = useState(false);

  const staff = useMemo(() => splitList(staffText), [staffText]);
  const request = (): DraftRequest => ({
    business_name: name.trim(), business_type: type, language, agent_name: agent.trim() || "Haanji",
    staff_role: role.trim() || undefined, greeting: greeting.trim() || undefined,
    staff,
    hours: Object.fromEntries(DAYS.map(([d]) => { const h = hours[d]; return [d, h && h.open ? [h.from, h.to] : null]; })),
    services: services.filter((s) => s.name.trim()).map((s) => ({
      name: s.name.trim(), duration_min: Number(s.duration) || 30, price_inr: s.price ? Number(s.price) : null,
      staff: s.staff.filter((p) => staff.includes(p)), aliases: splitList(s.aliases) })),
    places: splitList(placesText),
  });
  const note = (kind: "ok" | "bad", text: string) => setNotes((n) => [...n, { kind, text }]);

  async function build() {
    setBusy("draft"); setNotes([]); setResults([]); setSaved(false);
    try { const d = mode === "live" ? await engine.draft(request()) : previewDraft(request()); setDraft(d); if (d.problems.length) d.problems.forEach((p) => note("bad", p)); else note("ok", t("Pack \"{id}\" is ready, but it is not saved yet.", { id: d.pack_id })); }
    catch (e) { setDraft(null); note("bad", e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  }
  async function save() {
    if (!draft) return;
    setBusy("save");
    try { await engine.save(draft.pack_id, draft.yaml); setSaved(true); note("ok", t("Saved. Now run the scenarios.")); await refresh(); }
    catch (e) { note("bad", e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  }
  async function selftest() {
    if (!draft) return;
    setBusy("test"); setResults([]);
    try { const r = await engine.selftest(draft.pack_id); setResults(r.results); note(r.ok ? "ok" : "bad", r.summary || (r.ok ? t("All scenarios passed.") : t("See the failures above."))); }
    catch (e) { note("bad", e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  }
  const canNext = [name.trim().length > 1, staff.length > 0, Object.values(hours).some((h) => h.open), services.some((s) => s.name.trim()), true][step];
  const talkBase = status?.public_url || "/engine";

  if (mode !== "live" && mode !== "demo") {
    return <NotLive title={t("New shop")} sub={t("Five questions, one pack.")} demo={<p>{t("This page needs the live engine, because it really builds a pack.")}</p>} />;
  }

  return (
    <Page title={t("New shop")} sub={t("Five questions, and the agent is ready to answer your shop's phone.")}>
      {/* React Bits' Stepper draws the steps and slides between them; the
          buttons below stay ours, so "Aage" still waits for each step's answer. */}
      <Stepper step={step + 1} onStepChange={(n) => setStep(Math.min(Math.max(n, 1), STEPS.length) - 1)} linear showFooter={false}
               theme="light" accentColor="#1B3B8C" frame={false} width="100%" radius={12} className="onboard-stepper">

        <Step title={t(STEPS[0]!)}>
        <Panel title={t("1 · About the shop")}>
          <div className="body form">
            <label className="field"><span>{t("Business name")}</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("e.g. Smile Care Dental")} /></label>
            <div className="row">
              <label className="field"><span>{t("Kind of business")}</span><select className="input" value={type} onChange={(e) => setType(e.target.value)}>{TYPES.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}</select></label>
              <label className="field"><span>{t("Language")}</span><select className="input" value={language} onChange={(e) => setLanguage(e.target.value)}><option value="hinglish">Hinglish</option><option value="benglish">Benglish</option></select></label>
              <label className="field"><span>{t("Agent's name")}</span><input className="input" value={agent} onChange={(e) => setAgent(e.target.value)} /></label>
            </div>
            <label className="field"><span>{t("Greeting (leave empty and one is made for you)")}</span><input className="input" value={greeting} onChange={(e) => setGreeting(e.target.value)} placeholder={name ? `Haanji, ${name}. Main aapki kya madad karun?` : "Haanji, …"} /></label>
          </div>
        </Panel>
        </Step>
        <Step title={t(STEPS[1]!)}>
        <Panel title={t("2 · People")} hint={t("the people bookings are made with")}>
          <div className="body form">
            <label className="field"><span>{t("What they are called (doctor, stylist, teacher…)")}</span><input className="input" value={role} onChange={(e) => setRole(e.target.value)} placeholder={t("leave empty to use the business type")} /></label>
            <label className="field"><span>{t("Names, separated by commas")}</span><textarea className="input" rows={3} value={staffText} onChange={(e) => setStaffText(e.target.value)} placeholder="Dr Sheikh, Dr Mehta, Priya" /></label>
            <div className="chips">{staff.map((p) => <Chip key={p} kind="ok">{p}</Chip>)}</div>
          </div>
        </Panel>
        </Step>
        <Step title={t(STEPS[2]!)}>
        <Panel title={t("3 · Hours")} hint={t("untick the days you are closed")}>
          <div className="body form">
            {DAYS.map(([d, label]) => {
              const h = hours[d] ?? { open: false, from: "10:00", to: "20:00" };
              const set = (patch: Partial<DayHours>) => setHours((cur) => ({ ...cur, [d]: { ...h, ...patch } }));
              return (
                <div className="row hours" key={d}>
                  <label className="check"><input type="checkbox" checked={h.open} onChange={(e) => set({ open: e.target.checked })} /> {t(label)}</label>
                  <input className="input" type="time" value={h.from} disabled={!h.open} onChange={(e) => set({ from: e.target.value })} aria-label={t("{day} from", { day: t(label) })} />
                  <span className="muted">{t("to")}</span>
                  <input className="input" type="time" value={h.to} disabled={!h.open} onChange={(e) => set({ to: e.target.value })} aria-label={t("{day} until", { day: t(label) })} />
                  {!h.open && <span className="muted">{t("closed")}</span>}
                </div>
              );
            })}
          </div>
        </Panel>
        </Step>
        <Step title={t(STEPS[3]!)}>
        <Panel title="4 · Services" hint={t("name, how long, how much, who does it")} actions={<button className="btn btn-ghost btn-sm" onClick={() => setServices((s) => [...s, { name: "", duration: "30", price: "", staff: [], aliases: "" }])}>+ service</button>}>
          <div className="body form">
            {services.map((s, i) => {
              const set = (patch: Partial<ServiceRow>) => setServices((cur) => cur.map((x, j) => (j === i ? { ...x, ...patch } : x)));
              return (
                <div className="svc" key={i}>
                  <div className="row">
                    <label className="field grow"><span>Service</span><input className="input" value={s.name} onChange={(e) => set({ name: e.target.value })} placeholder="root canal" /></label>
                    <label className="field"><span>{t("Minutes")}</span><input className="input" type="number" min={5} value={s.duration} onChange={(e) => set({ duration: e.target.value })} /></label>
                    <label className="field"><span>₹</span><input className="input" type="number" min={0} value={s.price} onChange={(e) => set({ price: e.target.value })} placeholder={t("optional")} /></label>
                    {services.length > 1 && <button className="btn btn-ghost btn-sm" aria-label={t("remove")} onClick={() => setServices((cur) => cur.filter((_, j) => j !== i))}><Icon name="x" small /></button>}
                  </div>
                  <div className="row">
                    <div className="field"><span>{t("Who does it (none = everyone)")}</span><div className="chips">{staff.map((p) => (
                      <label key={p} className="check"><input type="checkbox" checked={s.staff.includes(p)} onChange={(e) => set({ staff: e.target.checked ? [...s.staff, p] : s.staff.filter((x) => x !== p) })} /> {p}</label>))}</div></div>
                    <label className="field grow"><span>{t("What else people call it (commas)")}</span><input className="input" value={s.aliases} onChange={(e) => set({ aliases: e.target.value })} placeholder="rct, rut kanal" /></label>
                  </div>
                </div>
              );
            })}
            <label className="field"><span>{t("Area / branch names (separated by commas). The recogniser mishears them, so we ask")}</span><input className="input" value={placesText} onChange={(e) => setPlacesText(e.target.value)} placeholder="Vijay Nagar, Bhawarkuan" /></label>
          </div>
        </Panel>
        </Step>
        <Step title={t(STEPS[4]!)}>
        <Panel title={t("5 · Ready")} hint={draft ? `pack ${draft.pack_id}${draft.exists ? t(" (already exists; saving overwrites it)") : ""}` : t("build the pack first")}
               actions={<>
                 <button className="btn btn-primary btn-sm" onClick={build} disabled={busy !== null}>{busy === "draft" ? t("Building…") : t("Build the pack")}</button>
                 {mode !== "live"
                   ? <Chip kind="muted" title={t("This is a preview: packs are saved on the live engine")}>{t("preview · saves on the live engine")}</Chip>
                   : isOwner
                   ? <button className="btn btn-ghost btn-sm" onClick={save} disabled={!draft || draft.problems.length > 0 || busy !== null}>{busy === "save" ? t("Saving…") : t("Save")}</button>
                   : <Chip kind="muted" title={t("Only the owner can save a pack")}>{t("only the owner saves")}</Chip>}
                 <button className="btn btn-ghost btn-sm" onClick={selftest} disabled={!draft || !saved || busy !== null}>{busy === "test" ? t("Running…") : t("Run the scenarios")}</button>
               </>}>
          <div className="body form">
            {mode !== "live" && <p className="note">{t("Sample mode: walk all five steps and see the pack HaanJi would build. Nothing is saved; on the live engine this pack goes straight onto the phone line.")}</p>}
            {notes.map((n, i) => <p key={i} className={n.kind === "ok" ? "note ok" : "note bad"}>{n.text}</p>)}
            {results.length > 0 && <ul className="results">{results.map((r, i) => <li key={i} className={r.passed ? "ok" : "bad"}>{r.passed ? "PASS" : "FAIL"} · {r.line}</li>)}</ul>}
            {draft && saved && (
              <div className="row">
                <a className="btn btn-primary" href={`${talkBase}/talk?pack=${encodeURIComponent(draft.pack_id)}`} target="_blank" rel="noopener noreferrer"><Icon name="phone" small /> {t("Make a test call")}</a>
                <button className="btn btn-ghost" onClick={() => setPack(draft.pack_id)}>{t("Use this pack in the console")}</button>
              </div>
            )}
            {draft && <details><summary>{t("See the YAML (you can edit it later in Pack Studio)")}</summary><pre className="yaml">{draft.yaml}</pre></details>}
          </div>
        </Panel>
        </Step>
      </Stepper>

      <div className="wizard-nav">
        <button className="btn btn-ghost" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>{t("Back")}</button>
        {step < STEPS.length - 1
          ? <button className="btn btn-primary" onClick={() => setStep((s) => s + 1)} disabled={!canNext}>{t("Next")} <Icon name="arrow" small /></button>
          : null}
      </div>
    </Page>
  );
}
