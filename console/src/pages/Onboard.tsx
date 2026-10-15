import { useMemo, useState } from "react";
import { engine } from "../engine";
import { useApp } from "../state";
import { Chip, Empty, Icon, Page, Panel } from "../components/Common";
import type { Draft, DraftRequest } from "../types";

const TYPES: [string, string][] = [["clinic", "Clinic / doctor"], ["salon", "Salon / spa"], ["lab", "Diagnostic lab"], ["coaching", "Coaching institute"], ["other", "Kuch aur"]];
const DAYS: [string, string][] = [["mon", "Som"], ["tue", "Mangal"], ["wed", "Budh"], ["thu", "Guru"], ["fri", "Shukra"], ["sat", "Shani"], ["sun", "Ravi"]];
const STEPS = ["Dukaan", "Log", "Timing", "Services", "Taiyaar"];

interface DayHours { open: boolean; from: string; to: string }
interface ServiceRow { name: string; duration: string; price: string; staff: string[]; aliases: string }

const splitList = (s: string) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);

export default function Onboard() {
  const { online, status, setPack, refresh } = useApp();
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
    try { const d = await engine.draft(request()); setDraft(d); if (d.problems.length) d.problems.forEach((p) => note("bad", p)); else note("ok", `Pack "${d.pack_id}" taiyaar hai — abhi save nahi hua.`); }
    catch (e) { setDraft(null); note("bad", e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  }
  async function save() {
    if (!draft) return;
    setBusy("save");
    try { await engine.save(draft.pack_id, draft.yaml); setSaved(true); note("ok", "Save ho gaya. Ab scenarios chalao."); await refresh(); }
    catch (e) { note("bad", e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  }
  async function selftest() {
    if (!draft) return;
    setBusy("test"); setResults([]);
    try { const r = await engine.selftest(draft.pack_id); setResults(r.results); note(r.ok ? "ok" : "bad", r.summary || (r.ok ? "Saare scenarios paas." : "Upar failures dekho.")); }
    catch (e) { note("bad", e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  }
  const canNext = [name.trim().length > 1, staff.length > 0, Object.values(hours).some((h) => h.open), services.some((s) => s.name.trim()), true][step];
  const talkBase = status?.public_url || "/engine";

  if (!online) {
    return <Page title="Nayi dukaan" sub="Paanch sawaal, ek pack."><Empty><p>Yeh page live engine ke bina kaam nahi karta — yeh sach mein ek pack banata hai.</p></Empty></Page>;
  }

  return (
    <Page title="Nayi dukaan" sub="Paanch sawaal, aur agent aapki dukaan ka phone uthane ko taiyaar.">
      <ol className="steps" aria-label="Steps">
        {STEPS.map((s, i) => <li key={s} className={i === step ? "on" : i < step ? "done" : undefined}><span>{i + 1}</span>{s}</li>)}
      </ol>

      {step === 0 && (
        <Panel title="1 · Dukaan ke baare mein">
          <div className="body form">
            <label className="field"><span>Business ka naam</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="jaise: Smile Care Dental" /></label>
            <div className="row">
              <label className="field"><span>Kis tarah ka business</span><select className="input" value={type} onChange={(e) => setType(e.target.value)}>{TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
              <label className="field"><span>Bhasha</span><select className="input" value={language} onChange={(e) => setLanguage(e.target.value)}><option value="hinglish">Hinglish</option><option value="benglish">Benglish</option></select></label>
              <label className="field"><span>Agent ka naam</span><input className="input" value={agent} onChange={(e) => setAgent(e.target.value)} /></label>
            </div>
            <label className="field"><span>Greeting (khali chhodo to apne aap banega)</span><input className="input" value={greeting} onChange={(e) => setGreeting(e.target.value)} placeholder={name ? `Haanji, ${name}. Main aapki kya madad karun?` : "Haanji, …"} /></label>
          </div>
        </Panel>
      )}
      {step === 1 && (
        <Panel title="2 · Log" hint="jinke naam se booking hogi">
          <div className="body form">
            <label className="field"><span>Inhe kya kehte hain (doctor, stylist, teacher…)</span><input className="input" value={role} onChange={(e) => setRole(e.target.value)} placeholder="khali chhodo to business type se" /></label>
            <label className="field"><span>Naam, comma se alag</span><textarea className="input" rows={3} value={staffText} onChange={(e) => setStaffText(e.target.value)} placeholder="Dr Sheikh, Dr Mehta, Priya" /></label>
            <div className="chips">{staff.map((p) => <Chip key={p} kind="ok">{p}</Chip>)}</div>
          </div>
        </Panel>
      )}
      {step === 2 && (
        <Panel title="3 · Timing" hint="jis din band ho, tick hata do">
          <div className="body form">
            {DAYS.map(([d, label]) => {
              const h = hours[d] ?? { open: false, from: "10:00", to: "20:00" };
              const set = (patch: Partial<DayHours>) => setHours((cur) => ({ ...cur, [d]: { ...h, ...patch } }));
              return (
                <div className="row hours" key={d}>
                  <label className="check"><input type="checkbox" checked={h.open} onChange={(e) => set({ open: e.target.checked })} /> {label}</label>
                  <input className="input" type="time" value={h.from} disabled={!h.open} onChange={(e) => set({ from: e.target.value })} aria-label={`${label} se`} />
                  <span className="muted">se</span>
                  <input className="input" type="time" value={h.to} disabled={!h.open} onChange={(e) => set({ to: e.target.value })} aria-label={`${label} tak`} />
                  {!h.open && <span className="muted">band</span>}
                </div>
              );
            })}
          </div>
        </Panel>
      )}
      {step === 3 && (
        <Panel title="4 · Services" hint="naam, kitna time, kitna daam, kaun karta hai" actions={<button className="btn btn-ghost btn-sm" onClick={() => setServices((s) => [...s, { name: "", duration: "30", price: "", staff: [], aliases: "" }])}>+ service</button>}>
          <div className="body form">
            {services.map((s, i) => {
              const set = (patch: Partial<ServiceRow>) => setServices((cur) => cur.map((x, j) => (j === i ? { ...x, ...patch } : x)));
              return (
                <div className="svc" key={i}>
                  <div className="row">
                    <label className="field grow"><span>Service</span><input className="input" value={s.name} onChange={(e) => set({ name: e.target.value })} placeholder="root canal" /></label>
                    <label className="field"><span>Minute</span><input className="input" type="number" min={5} value={s.duration} onChange={(e) => set({ duration: e.target.value })} /></label>
                    <label className="field"><span>₹</span><input className="input" type="number" min={0} value={s.price} onChange={(e) => set({ price: e.target.value })} placeholder="optional" /></label>
                    {services.length > 1 && <button className="btn btn-ghost btn-sm" aria-label="hatao" onClick={() => setServices((cur) => cur.filter((_, j) => j !== i))}><Icon name="x" small /></button>}
                  </div>
                  <div className="row">
                    <div className="field"><span>Kaun karta hai (koi nahi = sab)</span><div className="chips">{staff.map((p) => (
                      <label key={p} className="check"><input type="checkbox" checked={s.staff.includes(p)} onChange={(e) => set({ staff: e.target.checked ? [...s.staff, p] : s.staff.filter((x) => x !== p) })} /> {p}</label>))}</div></div>
                    <label className="field grow"><span>Log ise aur kya kehte hain (comma)</span><input className="input" value={s.aliases} onChange={(e) => set({ aliases: e.target.value })} placeholder="rct, rut kanal" /></label>
                  </div>
                </div>
              );
            })}
            <label className="field"><span>Ilaaka / branch ke naam (comma) — recogniser inhe galat sunta hai, isliye poochte hain</span><input className="input" value={placesText} onChange={(e) => setPlacesText(e.target.value)} placeholder="Vijay Nagar, Bhawarkuan" /></label>
          </div>
        </Panel>
      )}
      {step === 4 && (
        <Panel title="5 · Taiyaar" hint={draft ? `pack ${draft.pack_id}${draft.exists ? " (pehle se hai — save karne se overwrite hoga)" : ""}` : "pehle pack banao"}
               actions={<>
                 <button className="btn btn-primary btn-sm" onClick={build} disabled={busy !== null}>{busy === "draft" ? "Bana raha…" : "Pack banao"}</button>
                 <button className="btn btn-ghost btn-sm" onClick={save} disabled={!draft || draft.problems.length > 0 || busy !== null}>{busy === "save" ? "Save…" : "Save karo"}</button>
                 <button className="btn btn-ghost btn-sm" onClick={selftest} disabled={!draft || !saved || busy !== null}>{busy === "test" ? "Chal raha…" : "Scenarios chalao"}</button>
               </>}>
          <div className="body form">
            {notes.map((n, i) => <p key={i} className={n.kind === "ok" ? "note ok" : "note bad"}>{n.text}</p>)}
            {results.length > 0 && <ul className="results">{results.map((r, i) => <li key={i} className={r.passed ? "ok" : "bad"}>{r.passed ? "PASS" : "FAIL"} · {r.line}</li>)}</ul>}
            {draft && saved && (
              <div className="row">
                <a className="btn btn-primary" href={`${talkBase}/talk?pack=${encodeURIComponent(draft.pack_id)}`} target="_blank" rel="noopener noreferrer"><Icon name="phone" small /> Test call karo</a>
                <button className="btn btn-ghost" onClick={() => setPack(draft.pack_id)}>Console mein yeh pack chuno</button>
              </div>
            )}
            {draft && <details><summary>YAML dekho (Pack Studio mein baad mein bhi edit hoga)</summary><pre className="yaml">{draft.yaml}</pre></details>}
          </div>
        </Panel>
      )}

      <div className="wizard-nav">
        <button className="btn btn-ghost" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>Peeche</button>
        {step < STEPS.length - 1
          ? <button className="btn btn-primary" onClick={() => setStep((s) => s + 1)} disabled={!canNext}>Aage <Icon name="arrow" small /></button>
          : null}
      </div>
    </Page>
  );
}
