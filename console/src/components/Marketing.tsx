import { Link, useNavigate } from "react-router-dom";
import { t, useT } from "../i18n";
import { useApp } from "../state";
import { LangSwitch } from "./HeaderBits";
import { Icon } from "./Common";

/** The landing's own top bar: no app navigation, only what a visitor needs. */
export function MarketingBar() {
  const { status, setSampleView } = useApp();
  const nav = useNavigate();
  useT();
  const tryDemo = () => { setSampleView(true); nav("/dashboard"); };
  return (
    <header className="topbar mbar">
      <Link className="wordmark" to="/">HaanJi <span className="dev">हाँजी</span></Link>
      <nav className="mnav" aria-label={t("Site")}>
        <Link to="/how">{t("How it works")}</Link>
        <a href="/#plans">{t("Pricing")}</a>
      </nav>
      <div className="tools">
        <LangSwitch />
        <button type="button" className="btn btn-ghost btn-sm mbar-demo" onClick={tryDemo}>{t("Try demo")}</button>
        <Link className="btn btn-primary btn-sm" to="/dashboard">{status?.auth?.enabled ? t("Login") : t("Open the console")} <Icon name="arrow" small /></Link>
      </div>
    </header>
  );
}

/** The landing's footer: where the policies and the source are. */
export function SiteFooter() {
  const { status } = useApp();
  useT();
  return (
    <footer className="site-foot">
      <div>
        <b>HaanJi <span className="dev">हाँजी</span></b>
        <p className="muted">{t("An AI receptionist for clinics and coaching institutes: phone and WhatsApp, in the caller's language.")}</p>
      </div>
      <nav aria-label={t("Footer")}>
        <a href="/engine/privacy">{t("Privacy")}</a>
        <a href="/engine/my-data">{t("My data")}</a>
        <Link to="/how">{t("How it works")}</Link>
        <a href="https://github.com/aritra-25hazra/haanji" rel="noopener noreferrer" target="_blank">GitHub</a>
      </nav>
      <p className="muted small">{t("Version {v}", { v: status?.version ?? "1.2.0" })}</p>
    </footer>
  );
}
