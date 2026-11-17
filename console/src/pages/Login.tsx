import { useState } from "react";
import SplitText from "../components/SplitText";
import { engine } from "../engine";
import { t, useT } from "../i18n";
import { useApp } from "../state";
import { Icon } from "../components/Common";

/** Sign-in: the WhatsApp number is the account, a one-time code is the
 *  password. When the engine has no WhatsApp channel it hands the code back
 *  in the response, so the flow still works on a bare server. */
export default function Login() {
  const { signIn } = useApp();
  useT();
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
      if (r.dev_code) { setCode(r.dev_code); setNote(t("The engine gave the code here (WhatsApp is not connected): {code}", { code: r.dev_code })); }
      else setNote(r.channel === "whatsapp" ? t("The code is sent on WhatsApp (5 minutes).") : t("The code is sent."));
    } catch (e) { setNote(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  async function verify() {
    setBusy(true); setNote(null);
    try { const r = await engine.verifyOtp(phone, code); signIn(r.token, r.user); }
    catch { setNote(t("The code is wrong or has expired. Ask for a new one.")); }
    finally { setBusy(false); }
  }

  return (
    <div className="login">
      <div className="login-card">
        <span className="eyebrow">{t("Receptionist console")}</span>
        <SplitText key={t("Sign in")} tag="h1" text={t("Sign in")} trigger="load" splitType="chars" effect="rise" textAlign="left" delay={35} duration={0.7} />
        <p className="muted">{t("The WhatsApp number you are owner or staff with. No password: a one-time code comes to it.")}</p>
        {stage === "phone" ? (
          <form className="form" onSubmit={(e) => { e.preventDefault(); void sendCode(); }}>
            <label className="field"><span>WhatsApp number</span><input className="input" inputMode="numeric" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" autoFocus /></label>
            <button className="btn btn-primary" type="submit" disabled={busy || phone.replace(/\D/g, "").length < 10}>{t("Send the code")} <Icon name="arrow" small /></button>
          </form>
        ) : (
          <form className="form" onSubmit={(e) => { e.preventDefault(); void verify(); }}>
            <label className="field"><span>{t("6-digit code ({phone})", { phone })}</span><input className="input" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} autoFocus /></label>
            <div className="row">
              <button className="btn btn-primary" type="submit" disabled={busy || code.length < 6}>{t("Enter the console")} <Icon name="arrow" small /></button>
              <button className="btn btn-ghost" type="button" onClick={() => { setStage("phone"); setCode(""); }}>{t("Change the number")}</button>
            </div>
          </form>
        )}
        {note && <p className="muted" role="status">{note}</p>}
      </div>
    </div>
  );
}
