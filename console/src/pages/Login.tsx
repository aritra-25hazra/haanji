import { useState } from "react";
import SplitText from "../components/SplitText";
import { engine } from "../engine";
import { t, useT } from "../i18n";
import { useApp } from "../state";
import { Icon } from "../components/Common";

/** Sign-in. Email + password first; a one-time WhatsApp code is offered
 *  only while WhatsApp can actually deliver one. "Try demo" opens the
 *  made-up sample shop, read-only, with no account. */
export default function Login() {
  const { signIn, status, setSampleView } = useApp();
  useT();
  const waWorks = !!status?.whatsapp?.configured && status.whatsapp.last_send?.delivery?.status !== "failed";
  const [method, setMethod] = useState<"email" | "whatsapp">("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<"phone" | "code">("phone");
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function emailLogin() {
    setBusy(true); setNote(null);
    try { const r = await engine.login(email, password); signIn(r.token, r.user); }
    catch (e) { setNote(e instanceof Error && /429|too many/i.test(e.message) ? e.message : t("Wrong email or password.")); }
    finally { setBusy(false); }
  }
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
  const tryDemo = () => { setSampleView(true); window.history.pushState(null, "", "/dashboard"); window.dispatchEvent(new PopStateEvent("popstate")); };

  return (
    <div className="login">
      <div className="login-card">
        <span className="eyebrow">{t("Receptionist console")}</span>
        <SplitText key={t("Sign in")} tag="h1" text={t("Sign in")} trigger="load" splitType="chars" effect="rise" textAlign="left" delay={35} duration={0.7} />
        {method === "email" ? (
          <form className="form" onSubmit={(e) => { e.preventDefault(); void emailLogin(); }}>
            <label className="field"><span>{t("Email")}</span><input className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus /></label>
            <label className="field"><span>{t("Password")}</span><input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
            <button className="btn btn-primary" type="submit" disabled={busy || !email.includes("@") || password.length < 1}>{t("Enter the console")} <Icon name="arrow" small /></button>
            <p className="muted small">{t("Forgot the password? The person who set up your HaanJi can set a new one.")}</p>
          </form>
        ) : stage === "phone" ? (
          <form className="form" onSubmit={(e) => { e.preventDefault(); void sendCode(); }}>
            <p className="muted">{t("The WhatsApp number you are owner or staff with. No password: a one-time code comes to it.")}</p>
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
        <div className="row login-alt">
          {waWorks && (method === "email"
            ? <button className="btn btn-ghost btn-sm" type="button" onClick={() => { setMethod("whatsapp"); setNote(null); }}>{t("Use a WhatsApp code instead")}</button>
            : <button className="btn btn-ghost btn-sm" type="button" onClick={() => { setMethod("email"); setNote(null); }}>{t("Use email and password")}</button>)}
          <button className="btn btn-ghost btn-sm" type="button" onClick={tryDemo}>{t("Try the demo (no account)")}</button>
        </div>
      </div>
    </div>
  );
}
