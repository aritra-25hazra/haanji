import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Empty, Icon, Loading } from "./components/Common";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { useApp, type Mode } from "./state";
import Calendar from "./pages/Calendar";
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

interface NavItem { to: string; label: string; owner?: boolean; hint?: string }
// The shop's daily work stays in the bar; the engine's own pages (receipts,
// vocabulary, packs, latency) sit one click away so an owner is not asked
// to read eleven tabs to find today's bookings.
const LINKS: NavItem[] = [
  { to: "/dashboard", label: "Aaj" },
  { to: "/calendar", label: "Calendar" },
  { to: "/customers", label: "Customers" },
  { to: "/calls", label: "Calls" },
  { to: "/settings", label: "Settings", owner: true },
];
const ENGINE: NavItem[] = [
  { to: "/ledger", label: "Pramaan", hint: "har booking ki signed receipt" },
  { to: "/lexicon", label: "Bhasha", hint: "shabd jo agent pehchanta hai" },
  { to: "/packs", label: "Packs", hint: "kis business ke liye kya jaanta hai" },
  { to: "/studio", label: "Studio", hint: "pack badlo aur test karo" },
  { to: "/onboard", label: "Nayi dukaan", hint: "naya business 5 sawaal mein" },
  { to: "/ops", label: "Ops", hint: "speed, errors, counters" },
];

const PILL: Record<Mode, { text: string; title: string }> = {
  checking: { text: "…", title: "engine check ho raha hai" },
  live: { text: "LIVE", title: "engine se live" },
  demo: { text: "SAMPLE", title: "engine nahi mila, sample data" },
  offline: { text: "OFFLINE", title: "engine nahi mil raha; aap signed in ho, isliye sample nahi" },
};

export default function App() {
  const { mode, pack, packs, setPack, authRequired, user, isOwner, signOut } = useApp();
  const location = useLocation();
  if (authRequired) return <Suspense fallback={<Loading />}><Login /></Suspense>;
  const pill = PILL[mode];
  return (
    <>
      <header className="topbar">
        <Link className="wordmark" to="/dashboard">HaanJi <span className="dev">हाँजी</span></Link>
        <div className="navrow">
          <nav className="nav" aria-label="Main">
            {LINKS.filter((l) => !l.owner || isOwner).map((l) => (
              <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? "active" : undefined)}>{l.label}</NavLink>
            ))}
          </nav>
          <EngineMenu key={location.pathname} />
        </div>
        <div className="tools">
          <select aria-label="Pack" value={pack} onChange={(e) => setPack(e.target.value)}>
            {packs.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <span className={"live" + (mode === "live" ? "" : " off")} title={pill.title}><i />{pill.text}</span>
          <a href="/engine/talk" target="_blank" rel="noopener noreferrer" aria-label="Talk to HaanJi (nayi tab mein)"><span>Talk</span><Icon name="external" small /></a>
          {user && (
            <button className="who" onClick={signOut} title={`${user.phone} · ${user.role} · is device se sign out`}>
              <span>{user.name || user.phone}</span><small>{user.role}</small>
            </button>
          )}
        </div>
      </header>
      <main className="main" id="main">
        <ErrorBoundary resetKey={location.pathname}>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/calendar" element={<Calendar />} />
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
      </main>
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
              onClick={() => setOpen((o) => !o)}>
        {current ? `Engine · ${current.label}` : "Engine"}<Icon name="chevron" small />
      </button>
      {open && (
        <ul id="engine-pages" aria-label="Engine ke pages">
          {ENGINE.map((l) => (
            <li key={l.to}>
              <NavLink to={l.to} className={({ isActive }) => (isActive ? "active" : undefined)}>
                <b>{l.label}</b><span>{l.hint}</span>
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
  return (
    <Empty>
      <h2>Yeh page nahi hai</h2>
      <p className="muted mono">{pathname}</p>
      <Link className="btn btn-primary" to="/dashboard">Aaj pe wapas <Icon name="arrow" small /></Link>
    </Empty>
  );
}
