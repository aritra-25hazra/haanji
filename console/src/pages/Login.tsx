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
  const { signIn, status, setSampleView, loginError } = useApp();
  useT();
  const waWorks = !!status?.whatsapp?.configured && status.whatsapp.last_send?.delivery?.status !== "failed";
  const [method, setMethod] = useState<"email" | "whatsapp">("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<"phone" | "code">("phone");
  const [note, setNote] = useState<string | null>(
    loginError === "not-allowed" ? t("This Google account is not on this shop's list. Ask the owner to add your email.")
      : loginError ? t("Google sign-in did not finish. Try again, or use email and password.") : null);
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
      <a className="wordmark login-mark" href="/">HaanJi <span className="dev">हाँजी</span></a>
      <div className="login-card">
        <span className="eyebrow">{t("Receptionist console")}</span>
        <SplitText key={t("Sign in")} tag="h1" text={t("Sign in")} trigger="load" splitType="chars" effect="rise" textAlign="left" delay={35} duration={0.7} />
        {status?.auth?.google && method === "email" && (
          <>
            <a className="btn btn-ghost google-btn" href="/engine/api/auth/google/start">
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.8-5.5 3.8-3.3 0-6-2.7-6-6s2.7-6 6-6c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.8 3.4 14.6 2.5 12 2.5 6.8 2.5 2.5 6.8 2.5 12s4.3 9.5 9.5 9.5c5.5 0 9.1-3.9 9.1-9.3 0-.6-.1-1.1-.2-1.6H12z"/></svg>
              {t("Continue with Google")}
            </a>
            <p className="muted small or-line">{t("or")}</p>
          </>
        )}
        {method === "email" ? (
          <form className="form" onSubmit={(e) => { e.preventDefault(); void emailLogin(); }}>
            <label className="field"><span>{t("Email")}</span><input className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus /></label>
            <label className="field"><span>{t("Password")}</span><input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
            <button className="btn btn-primary" type="submit" disabled={busy || !email.includes("@") || password.length < 1}>{t("Enter the console")} <Icon name="arrow" small /></button>
            <p className="muted small">{status?.auth?.google
              ? t("Forgot the password? Use Continue with Google with the same email, or ask the person who set up your HaanJi for a new one.")
              : t("Forgot the password? The person who set up your HaanJi can set a new one.")}</p>
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
      <p className="login-tag">{t("The receptionist that answers your shop's phone in Hinglish.")}</p>
    </div>
  );
}
