import { useState } from "react";
import { engine } from "../engine";
import { useApp } from "../state";
import { Icon } from "../components/Common";

/** Sign-in: the WhatsApp number is the account, a one-time code is the
 *  password. When the engine has no WhatsApp channel it hands the code back
 *  in the response, so the flow still works on a bare server. */
export default function Login() {
  const { signIn } = useApp();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<"phone" | "code">("phone");
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function sendCode() {
    setBusy(true); setNote(null);
    try {
      const r = await engine.requestOtp(phone);
      setStage("code");
      if (r.dev_code) { setCode(r.dev_code); setNote(`Engine ne code yahin de diya (WhatsApp juda nahi): ${r.dev_code}`); }
      else setNote(r.channel === "whatsapp" ? "Code WhatsApp pe bheja hai (5 minute)." : "Code bheja gaya.");
    } catch (e) { setNote(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  async function verify() {
    setBusy(true); setNote(null);
    try { const r = await engine.verifyOtp(phone, code); signIn(r.token, r.user); }
    catch { setNote("Code galat ya expire ho gaya. Dobara mangwao."); }
    finally { setBusy(false); }
  }

  return (
    <div className="login">
      <div className="login-card">
        <span className="eyebrow">Receptionist console</span>
        <h1>Sign in</h1>
        <p className="muted">Jis WhatsApp number se aap owner ya staff hain, wahi number. Password nahi — ek baar ka code.</p>
        {stage === "phone" ? (
          <form className="form" onSubmit={(e) => { e.preventDefault(); void sendCode(); }}>
            <label className="field"><span>WhatsApp number</span><input className="input" inputMode="numeric" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" autoFocus /></label>
            <button className="btn btn-primary" type="submit" disabled={busy || phone.replace(/\D/g, "").length < 10}>Code bhejo <Icon name="arrow" small /></button>
          </form>
        ) : (
          <form className="form" onSubmit={(e) => { e.preventDefault(); void verify(); }}>
            <label className="field"><span>6-digit code ({phone})</span><input className="input" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} autoFocus /></label>
            <div className="row">
              <button className="btn btn-primary" type="submit" disabled={busy || code.length < 6}>Andar jao <Icon name="arrow" small /></button>
              <button className="btn btn-ghost" type="button" onClick={() => { setStage("phone"); setCode(""); }}>Number badlo</button>
            </div>
          </form>
        )}
        {note && <p className="muted" role="status">{note}</p>}
      </div>
    </div>
  );
}
