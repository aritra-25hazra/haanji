import { Suspense, lazy } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Empty, Icon, Loading } from "./components/Common";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { useApp, type Mode } from "./state";
import Calendar from "./pages/Calendar";
import Customers from "./pages/Customers";
import Settings from "./pages/Settings";
import Calls from "./pages/Calls";
import CallDetail from "./pages/CallDetail";
import Ledger from "./pages/Ledger";
import Lexicon from "./pages/Lexicon";
import Packs from "./pages/Packs";
import PackStudio from "./pages/PackStudio";
import Onboard from "./pages/Onboard";
import Login from "./pages/Login";

// The two chart pages carry recharts; they load when first opened.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Ops = lazy(() => import("./pages/Ops"));

interface NavItem { to: string; label: string; owner?: boolean }
const LINKS: NavItem[] = [
  { to: "/dashboard", label: "Aaj" },
  { to: "/calendar", label: "Calendar" },
  { to: "/customers", label: "Customers" },
  { to: "/calls", label: "Calls" },
  { to: "/ledger", label: "Pramaan" },
  { to: "/lexicon", label: "Bhasha" },
  { to: "/packs", label: "Packs" },
  { to: "/studio", label: "Studio" },
  { to: "/onboard", label: "Nayi dukaan" },
  { to: "/ops", label: "Ops" },
  { to: "/settings", label: "Settings", owner: true },
];

const PILL: Record<Mode, { text: string; title: string }> = {
  checking: { text: "…", title: "engine check ho raha hai" },
  live: { text: "LIVE", title: "engine se live" },
  demo: { text: "SAMPLE", title: "engine nahi mila — sample data" },
  offline: { text: "OFFLINE", title: "engine nahi mil raha — signed in, isliye sample nahi" },
};

export default function App() {
  const { mode, pack, packs, setPack, authRequired, user, isOwner, signOut } = useApp();
  const location = useLocation();
  if (authRequired) return <Login />;
  const pill = PILL[mode];
  return (
    <>
      <header className="topbar">
        <Link className="wordmark" to="/dashboard">HaanJi <span className="dev">हाँजी</span></Link>
        <nav className="nav" aria-label="Main">
          {LINKS.filter((l) => !l.owner || isOwner).map((l) => (
            <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? "active" : undefined)}>{l.label}</NavLink>
          ))}
        </nav>
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
