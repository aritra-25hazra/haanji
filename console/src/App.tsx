import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { isOffline } from "./api";
import Dashboard from "./pages/Dashboard";
import Calls from "./pages/Calls";
import CallDetail from "./pages/CallDetail";
import Ledger from "./pages/Ledger";
import Lexicon from "./pages/Lexicon";
import Packs from "./pages/Packs";
import PackStudio from "./pages/PackStudio";

const LINKS: [string, string][] = [
  ["/dashboard", "Dashboard"],
  ["/calls", "Calls"],
  ["/ledger", "Pramaan ledger"],
  ["/lexicon", "Bhasha lexicon"],
  ["/packs", "Vertical pack"],
  ["/studio", "Pack Studio"],
];

export default function App() {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">Haan<span>ji</span></div>
        <div className="brand-sub">Smile Care Dental</div>
        <nav className="nav">
          {LINKS.map(([to, label]) => (
            <NavLink key={to} to={to}
              className={({ isActive }) => (isActive ? "active" : undefined)}>
              {label}
            </NavLink>
          ))}
          <a href="http://localhost:8090/talk" target="_blank" rel="noopener noreferrer">
            Talk to HaanJi ↗
          </a>
          <a href="http://localhost:8090/whatsapp" target="_blank" rel="noopener noreferrer">
            WhatsApp demo ↗
          </a>
        </nav>
        <footer>v0.4.0 · {isOffline() ? "local demo" : "live"}</footer>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/calls" element={<Calls />} />
          <Route path="/calls/:id" element={<CallDetail />} />
          <Route path="/ledger" element={<Ledger />} />
          <Route path="/lexicon" element={<Lexicon />} />
          <Route path="/packs" element={<Packs />} />
          <Route path="/studio" element={<PackStudio />} />
        </Routes>
      </main>
    </div>
  );
}
