import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Icon } from "./components/Common";
import { useApp } from "./state";
import Dashboard from "./pages/Dashboard";
import Calls from "./pages/Calls";
import CallDetail from "./pages/CallDetail";
import Ledger from "./pages/Ledger";
import Lexicon from "./pages/Lexicon";
import Packs from "./pages/Packs";
import PackStudio from "./pages/PackStudio";
import Onboard from "./pages/Onboard";

const LINKS: [string, string][] = [
  ["/dashboard", "Aaj"], ["/calls", "Calls"], ["/ledger", "Pramaan"],
  ["/lexicon", "Bhasha"], ["/packs", "Packs"], ["/studio", "Studio"], ["/onboard", "Nayi dukaan"],
];

export default function App() {
  const { online, checked, pack, packs, setPack } = useApp();
  return (
    <>
      <header className="topbar">
        <Link className="wordmark" to="/dashboard">HaanJi <span className="dev">हाँजी</span></Link>
        <nav className="nav" aria-label="Main">
          {LINKS.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : undefined)}>{label}</NavLink>
          ))}
        </nav>
        <div className="tools">
          <select aria-label="Pack" value={pack} onChange={(e) => setPack(e.target.value)}>
            {packs.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <span className={"live" + (online ? "" : " off")} title={online ? "engine se live" : checked ? "sample data" : "checking"}>
            <i />{online ? "LIVE" : checked ? "SAMPLE" : "…"}
          </span>
          <a href="/engine/talk" target="_blank" rel="noopener noreferrer" aria-label="Talk to HaanJi (nayi tab mein)"><span>Talk</span><Icon name="external" small /></a>
        </div>
      </header>
      <main className="main" id="main">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/calls" element={<Calls />} />
          <Route path="/calls/:id" element={<CallDetail />} />
          <Route path="/ledger" element={<Ledger />} />
          <Route path="/lexicon" element={<Lexicon />} />
          <Route path="/packs" element={<Packs />} />
          <Route path="/studio" element={<PackStudio />} />
          <Route path="/onboard" element={<Onboard />} />
        </Routes>
      </main>
    </>
  );
}
