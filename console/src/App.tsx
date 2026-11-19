import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Empty, Icon, Loading } from "./components/Common";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { HelpChat } from "./components/HelpChat";
import { MarketingBar, SiteFooter } from "./components/Marketing";
import { AiChip, LangSwitch } from "./components/HeaderBits";
import { packLabel, packShort } from "./labels";
import { en, t, useLang } from "./i18n";
import { useApp, type Mode } from "./state";
import Calendar from "./pages/Calendar";
import Queue from "./pages/Queue";
import Customers from "./pages/Customers";
import Settings from "./pages/Settings";
import Calls from "./pages/Calls";
import CallDetail from "./pages/CallDetail";
import Lexicon from "./pages/Lexicon";
import Packs from "./pages/Packs";
import PackStudio from "./pages/PackStudio";

// The chart pages carry recharts and the animated ones gsap or motion; each
// loads when first opened, so the first paint ships neither.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Ops = lazy(() => import("./pages/Ops"));
const Ledger = lazy(() => import("./pages/Ledger"));
const Onboard = lazy(() => import("./pages/Onboard"));
const Login = lazy(() => import("./pages/Login"));
const Home = lazy(() => import("./pages/Home"));
const HowItWorks = lazy(() => import("./pages/HowItWorks"));

interface NavItem { to: string; label: string; owner?: boolean; hint?: string }
// The shop's daily work stays in the bar; the engine's own pages (receipts,
// vocabulary, packs, latency) sit one click away so an owner is not asked
// to read eleven tabs to find today's bookings.
const LINKS: NavItem[] = [
  { to: "/dashboard", label: en("Today") },
  { to: "/calendar", label: en("Calendar") },
  { to: "/queue", label: en("Queue") },
  { to: "/customers", label: en("Customers") },
  { to: "/calls", label: en("Calls") },
  { to: "/settings", label: en("Settings"), owner: true },
];
const ENGINE: NavItem[] = [
  { to: "/how", label: en("How it works"), hint: en("one call step by step, and what was measured") },
  { to: "/ledger", label: "Pramaan", hint: en("a signed receipt for every booking") },
  { to: "/lexicon", label: "Bhasha", hint: en("the words the agent knows") },
  { to: "/packs", label: en("Packs"), hint: en("what it knows for each kind of business") },
  { to: "/studio", label: en("Studio"), hint: en("change a pack and test it") },
  { to: "/onboard", label: en("New shop"), hint: en("a new business in 5 questions") },
  { to: "/ops", label: "Ops", hint: en("speed, errors, counters") },
];

const PILL: Record<Mode, { text: string; title: string }> = {
  checking: { text: "…", title: en("checking the engine") },
  live: { text: "LIVE", title: en("live from the engine") },
  demo: { text: "SAMPLE", title: en("sample data") },
  offline: { text: "OFFLINE", title: en("the engine cannot be reached") },
};

export default function App() {
  const { mode, pack, packs, setPack, authRequired, user, isOwner, signOut, sampleView, setSampleView } = useApp();
  const location = useLocation();
  const lang = useLang();
  const [menuFor, setMenuFor] = useState<string | null>(null);   // the path the phone menu was opened on
  const menuOpen = menuFor === location.pathname;                // a navigation closes it
  // On a phone the tabs scroll sideways; keep the current one in view.
  useEffect(() => {
    document.querySelector(".nav a.active")?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [location.pathname]);
  // The landing ("/", and How it works for a visitor) has its own bar and no app nav.
  const marketing = !user && (location.pathname === "/" || (location.pathname === "/how" && !sampleView));
  // The sample shop ("Try demo") needs no sign-in: it is made up and read-only.
  if (authRequired && !sampleView && !marketing) return <Suspense fallback={<Loading />}><Login /></Suspense>;
  const pill = PILL[mode];
  const routes = (
    <ErrorBoundary resetKey={location.pathname}>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/" element={user ? <Navigate to="/dashboard" replace /> : <Home />} />
          <Route path="/how" element={<HowItWorks />} />
          <Route path="/login" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/queue" element={<Queue />} />
          <Route path="/customers" element={<Customers />} />
          <Route path="/calls" element={<Calls />} />
          <Route path="/calls/:id" element={<CallDetail />} />
          <Route path="/ledger" element={<Ledger />} />
          <Route path="/lexicon" element={<Lexicon />} />
          <Route path="/packs" element={<Packs />} />
          <Route path="/studio" element={<PackStudio />} />
          <Route path="/onboard" element={<Onboard />} />
          <Route path="/ops" element={<Ops />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
  if (marketing) {
    return (
      <>
        <MarketingBar />
        <main className="main marketing" id="main">{routes}</main>
        <SiteFooter />
        <HelpChat />
      </>
    );
  }
  return (
    <>
      <header className="topbar">
        <Link className="wordmark" to={user ? "/dashboard" : "/"}>HaanJi <span className="dev">हाँजी</span></Link>
        <button type="button" className="menu-btn" aria-expanded={menuOpen} aria-controls="app-nav"
                onClick={() => setMenuFor(menuOpen ? null : location.pathname)}>
          <Icon name={menuOpen ? "x" : "chevron"} small />{t("Menu")}
        </button>
        <div className={"navrow" + (menuOpen ? " open" : "")} id="app-nav">
          <nav className="nav" aria-label="Main">
            {LINKS.filter((l) => !l.owner || isOwner).map((l) => (
              <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? "active" : undefined)}>{t(l.label)}</NavLink>
            ))}
          </nav>
          {isOwner && <EngineMenu key={location.pathname + lang} />}
        </div>
        <div className="tools">
          <select aria-label="Pack" value={pack} onChange={(e) => setPack(e.target.value)}>
            {packs.map((p) => <option key={p} value={p} title={packLabel(p)}>{packShort(p)}</option>)}
          </select>
          <button type="button" className="sample-switch" aria-pressed={sampleView} onClick={() => setSampleView(!sampleView)}
                  title={sampleView ? t("Back to real data") : t("Show a made-up shop with 100 customers (for a demo)")}>
            <i aria-hidden="true" />Sample
          </button>
          {!sampleView && <span className={"live" + (mode === "live" ? "" : " off")} title={t(pill.title)}><i />{pill.text}</span>}
          <AiChip />
          <LangSwitch />
          <a href="/engine/talk" target="_blank" rel="noopener noreferrer" aria-label={t("Talk to HaanJi (opens a new tab)")}><span>Talk</span><Icon name="external" small /></a>
          {user && (
            <button className="who" onClick={signOut} title={t("{phone} · {role} · sign out on this device", { phone: user.phone, role: user.role })}>
              <span>{user.name || user.phone}</span><small>{user.role}</small>
            </button>
          )}
        </div>
      </header>
      <main className="main" id="main">{routes}</main>
      <HelpChat />
    </>
  );
}

/** The engine's pages behind one button. Keyed by the path, so a navigation
 *  always closes it; Escape and a click outside close it too. */
function EngineMenu() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const current = ENGINE.find((l) => pathname.startsWith(l.to));
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); box.current?.querySelector("button")?.focus(); } };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div className="engine-menu" ref={box}>
      <button type="button" className={current ? "active" : undefined} aria-expanded={open} aria-controls="engine-pages"
              aria-label={current ? t("Admin pages: {page}", { page: t(current.label) }) : t("Admin pages")}
              onClick={() => setOpen((o) => !o)}>
        {current ? t(current.label) : t("Admin")}<Icon name="chevron" small />
      </button>
      {open && (
        <ul id="engine-pages" aria-label={t("Admin pages")}>
          {ENGINE.map((l) => (
            <li key={l.to}>
              <NavLink to={l.to} className={({ isActive }) => (isActive ? "active" : undefined)}>
                <b>{t(l.label)}</b><span>{l.hint && t(l.hint)}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NotFound() {
  const { pathname } = useLocation();
  useLang();
  return (
    <Empty>
      <h2>{t("This page does not exist")}</h2>
      <p className="muted mono">{pathname}</p>
      <Link className="btn btn-primary" to="/dashboard">{t("Back to today")} <Icon name="arrow" small /></Link>
    </Empty>
  );
}

