import { useState } from "react";
import SplitText from "../components/SplitText";
import { engine, type SignedIn } from "../engine";
import { t, useT } from "../i18n";
import { useApp } from "../state";
import { Icon } from "../components/Common";

type View = "password" | "emailcode" | "whatsapp" | "reset";

/** Sign-in. Email + password first. A code by email (and a password reset
 *  with one) is offered once the server can send mail; a WhatsApp code only
 *  while WhatsApp can actually deliver one. With two-step sign-in on, any
 *  first step ends at a code from the authenticator app. "Try demo" opens the
 *  made-up sample shop, read-only, with no account. */
export default function Login() {
  const { signIn, status, setSampleView, loginError, loginTicket } = useApp();
  useT();
  const waWorks = !!status?.whatsapp?.configured && status.whatsapp.last_send?.delivery?.status !== "failed";
  const mailWorks = !!status?.auth?.email_codes;
  const [view, setView] = useState<View>("password");
  const [stage, setStage] = useState<"ask" | "code">("ask");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fresh, setFresh] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [ticket, setTicket] = useState<string | null>(loginTicket);
  const [second, setSecond] = useState("");
  const [note, setNote] = useState<string | null>(
    loginError === "not-allowed" ? t("This Google account is not on this shop's list. Ask the owner to add your email.")
      : loginError ? t("Google sign-in did not finish. Try again, or use email and password.") : null);
  const [busy, setBusy] = useState(false);

  const go = (v: View) => { setView(v); setStage("ask"); setCode(""); setNote(null); };
  const finish = (r: SignedIn) => {
    if (r.needs_2fa) { setTicket(r.ticket); setSecond(""); setNote(null); }
    else signIn(r.token, r.user);
  };
  async function run(work: () => Promise<void>, onError: (e: unknown) => string) {
    setBusy(true); setNote(null);
    try { await work(); } catch (e) { setNote(onError(e)); } finally { setBusy(false); }
  }
  const tooMany = (e: unknown) => e instanceof Error && /429|too many/i.test(e.message);
  const said = (e: unknown) => (e instanceof Error ? e.message : String(e));

  const passwordLogin = () => run(async () => finish(await engine.login(email, password)),
    (e) => (tooMany(e) ? said(e) : t("Wrong email or password.")));
  const sendWhatsApp = () => run(async () => {
    const r = await engine.requestOtp(phone);
    setStage("code");
    if (r.dev_code) { setCode(r.dev_code); setNote(t("The engine gave the code here (WhatsApp is not connected): {code}", { code: r.dev_code })); }
    else setNote(r.channel === "whatsapp" ? t("The code is sent on WhatsApp (5 minutes).") : t("The code is sent."));
  }, said);
  const verifyWhatsApp = () => run(async () => finish(await engine.verifyOtp(phone, code)),
    () => t("The code is wrong or has expired. Ask for a new one."));
  const sendEmail = (purpose: "login" | "reset") => run(async () => {
    const r = await engine.emailCode(email, purpose);
    setStage("code");
    if (r.dev_code) { setCode(r.dev_code); setNote(t("The engine gave the code here (email is not set up): {code}", { code: r.dev_code })); }
    else setNote(t("If this email has an account, a code is on its way (5 minutes). Look in spam too."));
  }, said);
  const verifyEmail = () => run(async () => finish(await engine.emailVerify(email, code)),
    () => t("The code is wrong or has expired. Ask for a new one."));
  const reset = () => run(async () => {
    await engine.resetPassword(email, code, fresh);
    setView("password"); setStage("ask"); setCode(""); setPassword(""); setFresh("");
    setNote(t("Password changed. Every device was signed out; sign in with the new password."));
  }, (e) => (e instanceof Error && /at least|not the email/.test(e.message) ? said(e) : t("The code is wrong or has expired. Ask for a new one.")));
  const verifySecond = () => run(async () => { const r = await engine.twofaVerify(ticket!, second); signIn(r.token, r.user); },
    () => t("That code is not right, or this sign-in took over 5 minutes. Type the newest code from the app (or a recovery code), or start again."));
  const tryDemo = () => { setSampleView(true); window.history.pushState(null, "", "/dashboard"); window.dispatchEvent(new PopStateEvent("popstate")); };

  const emailField = (
    <label className="field"><span>{t("Email")}</span><input className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus /></label>
  );
  const codeField = (label: string) => (
    <label className="field"><span>{label}</span><input className="input" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value.trim())} maxLength={6} autoFocus /></label>
  );
  const enter = (ready: boolean) => (
    <button className="btn btn-primary" type="submit" disabled={busy || !ready}>{t("Enter the console")} <Icon name="arrow" small /></button>
  );

  let form;
  if (ticket) {
    form = (
      <form className="form" onSubmit={(e) => { e.preventDefault(); void verifySecond(); }}>
        <p className="muted">{t("Two-step sign-in is on. Open your authenticator app and type the 6-digit code for HaanJi. Lost the phone? Type one of your recovery codes.")}</p>
        <label className="field"><span>{t("Code from the app")}</span>
          <input className="input" autoComplete="one-time-code" value={second} onChange={(e) => setSecond(e.target.value)} maxLength={20} autoFocus /></label>
        <div className="row">
          {enter(second.replace(/\W/g, "").length >= 6)}
          <button className="btn btn-ghost" type="button" onClick={() => { setTicket(null); setSecond(""); setNote(null); }}>{t("Start again")}</button>
        </div>
      </form>
    );
  } else if (view === "password") {
    form = (
      <form className="form" onSubmit={(e) => { e.preventDefault(); void passwordLogin(); }}>
        {emailField}
        <label className="field"><span>{t("Password")}</span><input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {enter(email.includes("@") && password.length > 0)}
        {mailWorks
          ? <button className="btn btn-ghost btn-sm link-btn" type="button" onClick={() => go("reset")}>{t("Forgot the password?")}</button>
          : <p className="muted small">{status?.auth?.google
            ? t("Forgot the password? Use Continue with Google with the same email, or ask the person who set up your HaanJi for a new one.")
            : t("Forgot the password? The person who set up your HaanJi can set a new one.")}</p>}
      </form>
    );
  } else if (view === "emailcode") {
    form = stage === "ask" ? (
      <form className="form" onSubmit={(e) => { e.preventDefault(); void sendEmail("login"); }}>
        <p className="muted">{t("No password: a one-time code comes to your email.")}</p>
        {emailField}
        <button className="btn btn-primary" type="submit" disabled={busy || !email.includes("@")}>{t("Send the code")} <Icon name="arrow" small /></button>
      </form>
    ) : (
      <form className="form" onSubmit={(e) => { e.preventDefault(); void verifyEmail(); }}>
        {codeField(t("6-digit code ({email})", { email }))}
        <div className="row">
          {enter(code.length === 6)}
          <button className="btn btn-ghost" type="button" onClick={() => { setStage("ask"); setCode(""); }}>{t("Change the email")}</button>
        </div>
      </form>
    );
  } else if (view === "reset") {
    form = stage === "ask" ? (
      <form className="form" onSubmit={(e) => { e.preventDefault(); void sendEmail("reset"); }}>
        <p className="muted">{t("A reset code comes to the email you sign in with. Then you choose a new password.")}</p>
        {emailField}
        <div className="row">
          <button className="btn btn-primary" type="submit" disabled={busy || !email.includes("@")}>{t("Send the reset code")} <Icon name="arrow" small /></button>
          <button className="btn btn-ghost" type="button" onClick={() => go("password")}>{t("Back")}</button>
        </div>
      </form>
    ) : (
      <form className="form" onSubmit={(e) => { e.preventDefault(); void reset(); }}>
        {codeField(t("6-digit code ({email})", { email }))}
        <label className="field"><span>{t("New password (at least 10 characters)")}</span>
          <input className="input" type="password" autoComplete="new-password" value={fresh} onChange={(e) => setFresh(e.target.value)} minLength={10} /></label>
        <div className="row">
          <button className="btn btn-primary" type="submit" disabled={busy || code.length !== 6 || fresh.length < 10}>{t("Set the new password")}</button>
          <button className="btn btn-ghost" type="button" onClick={() => go("password")}>{t("Back")}</button>
        </div>
      </form>
    );
  } else {
    form = stage === "ask" ? (
      <form className="form" onSubmit={(e) => { e.preventDefault(); void sendWhatsApp(); }}>
        <p className="muted">{t("The WhatsApp number you are owner or staff with. No password: a one-time code comes to it.")}</p>
        <label className="field"><span>WhatsApp number</span><input className="input" inputMode="numeric" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" autoFocus /></label>
        <button className="btn btn-primary" type="submit" disabled={busy || phone.replace(/\D/g, "").length < 10}>{t("Send the code")} <Icon name="arrow" small /></button>
      </form>
    ) : (
      <form className="form" onSubmit={(e) => { e.preventDefault(); void verifyWhatsApp(); }}>
        {codeField(t("6-digit code ({phone})", { phone }))}
        <div className="row">
          {enter(code.length === 6)}
          <button className="btn btn-ghost" type="button" onClick={() => { setStage("ask"); setCode(""); }}>{t("Change the number")}</button>
        </div>
      </form>
    );
  }

  return (
    <div className="login">
      <a className="wordmark login-mark" href="/">HaanJi <span className="dev">हाँजी</span></a>
      <div className="login-card">
        <span className="eyebrow">{t("Receptionist console")}</span>
        <SplitText key={t("Sign in")} tag="h1" text={t("Sign in")} trigger="load" splitType="chars" effect="rise" textAlign="left" delay={35} duration={0.7} />
        {status?.auth?.google && view === "password" && !ticket && (
          <>
            <a className="btn btn-ghost google-btn" href="/engine/api/auth/google/start">
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.8-5.5 3.8-3.3 0-6-2.7-6-6s2.7-6 6-6c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.8 3.4 14.6 2.5 12 2.5 6.8 2.5 2.5 6.8 2.5 12s4.3 9.5 9.5 9.5c5.5 0 9.1-3.9 9.1-9.3 0-.6-.1-1.1-.2-1.6H12z"/></svg>
              {t("Continue with Google")}
            </a>
            <p className="muted small or-line">{t("or")}</p>
          </>
        )}
        {form}
        {note && <p className="muted" role="status">{note}</p>}
        <div className="row login-alt">
          {!ticket && view !== "password" && view !== "reset" &&
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => go("password")}>{t("Use email and password")}</button>}
          {!ticket && mailWorks && view !== "emailcode" && view !== "reset" &&
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => go("emailcode")}>{t("Email me a code instead")}</button>}
          {!ticket && waWorks && view !== "whatsapp" && view !== "reset" &&
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => go("whatsapp")}>{t("Use a WhatsApp code instead")}</button>}
          <button className="btn btn-ghost btn-sm" type="button" onClick={tryDemo}>{t("Try the demo (no account)")}</button>
        </div>
      </div>
      <p className="login-tag">{t("The receptionist that answers your shop's phone in Hinglish.")}</p>
    </div>
  );
}
