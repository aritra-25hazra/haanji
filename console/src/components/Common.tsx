import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { useApp } from "../state";
import { engine, devanagariWanted, setDevanagariWanted } from "../engine";

const REDUCED = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

// ── icons: one family, inline SVG ──────────────────────────────────────────
const PATHS: Record<string, string> = {
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6.2 6.2l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
  mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/>',
  bolt: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  arrow: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
  back: '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  chevron: '<polyline points="6 9 12 15 18 9"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.5 15a9 9 0 1 1-2.1-9.4L23 10"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
  bell: '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  rupee: '<path d="M6 3h12"/><path d="M6 8h12"/><path d="M6 13l8.5 8"/><path d="M6 13h3"/><path d="M9 13c6.667 0 6.667-10 0-10"/>',
};

export function Icon({ name, small = false }: { name: string; small?: boolean }) {
  return (
    <svg className={small ? "icon-sm" : "icon"} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: PATHS[name] ?? "" }} />
  );
}

// ── layout ─────────────────────────────────────────────────────────────────
export function Page({ title, sub, actions, children }:
  { title: string; sub?: string; actions?: ReactNode; children: ReactNode }) {
  const { mode, refresh } = useApp();
  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">{title}</h1>
          {sub && <p className="page-sub">{sub}</p>}
        </div>
        {actions && <div className="row">{actions}</div>}
      </div>
      {mode === "demo" && (
        <div className="banner" role="status" data-testid="sample-banner">
          <Icon name="refresh" small />
          Engine se connect nahi ho pa raha — sample data dikha raha hoon. Thodi der mein dobara try karo.
        </div>
      )}
      {mode === "offline" && (
        <div className="banner bad" role="alert" data-testid="offline-banner">
          <Icon name="x" small />
          <span>Engine se connect nahi ho pa raha. Aap signed-in hain, isliye sample data nahi dikhaunga — asli numbers engine wapas aate hi.</span>
          <button className="btn btn-ghost btn-sm" onClick={() => void refresh()}>Dobara try karo</button>
        </div>
      )}
      {children}
    </>
  );
}

/** What a page shows while it cannot read from the engine: a checking state
 *  first, then either the demo note or the offline note. */
export function NotLive({ title, sub, demo }: { title: string; sub?: string; demo?: ReactNode }) {
  const { mode } = useApp();
  return (
    <Page title={title} sub={sub}>
      {mode === "checking"
        ? <Checking />
        : mode === "demo"
          ? <Empty>{demo ?? <p>Yeh page live engine ke bina kaam nahi karta.</p>}</Empty>
          : <Empty><p>Engine wapas aate hi yeh page bhar jayega.</p></Empty>}
    </Page>
  );
}

export function Checking() {
  return <div className="loading" role="status" aria-live="polite">Engine check ho raha hai…</div>;
}

export function Panel({ title, hint, actions, children }:
  { title: string; hint?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel">
      <header>
        <h2>{title}</h2>
        <div className="row">{hint && <span className="hint">{hint}</span>}{actions}</div>
      </header>
      {children}
    </section>
  );
}

export function useCountUp(target: number, ms = 400): number {
  const [n, setN] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    if (REDUCED) return;
    const start = performance.now(), a = from.current, b = target;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / ms), e = 1 - Math.pow(1 - p, 3);
      setN(a + (b - a) * e);
      if (p < 1) raf = requestAnimationFrame(tick); else from.current = b;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return REDUCED ? target : n;
}

function CountUp({ value, decimals }: { value: number; decimals: number }) {
  const n = useCountUp(value);
  return <>{n.toLocaleString("en-IN", { maximumFractionDigits: decimals, minimumFractionDigits: decimals })}</>;
}

/** A number on the wall. In the demo it carries a SAMPLE watermark, so a
 *  screenshot can never pass a sample figure off as a real one. */
export function Tile({ label, value, foot, mono = false, decimals = 0, prefix = "", suffix = "", index = 0 }:
  { label: string; value: ReactNode | number; foot?: string; mono?: boolean; decimals?: number; prefix?: string; suffix?: string; index?: number }) {
  const { mode } = useApp();
  const sample = mode === "demo";
  return (
    <div className={"tile" + (sample ? " sample" : "")} data-reveal style={{ "--i": index } as CSSProperties}>
      {sample && <span className="watermark" aria-label="sample data">SAMPLE</span>}
      <h3>{label}</h3>
      <div className={"value" + (mono ? " mono" : "")}>
        {typeof value === "number" ? <>{prefix}<CountUp value={value} decimals={decimals} />{suffix}</> : value}
      </div>
      {foot && <div className="foot">{foot}</div>}
    </div>
  );
}

export type ChipKind = "ok" | "warn" | "bad" | "muted" | "ink";

export function Chip({ kind, mono = false, title, children }:
  { kind?: ChipKind; mono?: boolean; title?: string; children: ReactNode }) {
  return <span className={"chip" + (kind ? ` ${kind}` : "") + (mono ? " mono" : "")} title={title}>{children}</span>;
}

const OUTCOME_KIND: Record<string, ChipKind | undefined> = {
  BOOKED: "ok", RESCHEDULED: "ok", FAQ_ANSWERED: undefined, LEAD_CAPTURED: "warn", HANDED_OFF: "bad",
  REFUSED: "ink", ABANDONED: "muted", IN_PROGRESS: "muted",
};
export function OutcomeChip({ outcome }: { outcome: string | null }) {
  const o = outcome || "IN_PROGRESS";
  return <Chip kind={OUTCOME_KIND[o]}>{o.replace(/_/g, " ").toLowerCase()}</Chip>;
}

export function Stamp({ tone = "red", big = false, children }:
  { tone?: "red" | "leaf"; big?: boolean; children: ReactNode }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || REDUCED || typeof el.animate !== "function") return;
    const rot = big ? "rotate(-1.5deg)" : "rotate(-3deg)";
    const a = el.animate([
      { transform: `${rot} scale(1.35)`, opacity: 0 }, { opacity: 1, offset: .6 },
      { opacity: .8, offset: .7 }, { transform: `${rot} scale(1)`, opacity: 1 },
    ], { duration: 400, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" });
    return () => a.cancel();
  }, [big, children]);
  return <span ref={ref} className={"stamp" + (tone === "leaf" ? " leaf" : "") + (big ? " big" : "")}>{children}</span>;
}

export function Repair({ c }: { c: { from_token: string; to_surface: string; asr_confidence?: number } }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const s = ref.current;
    const path = s?.querySelector("path");
    if (!path || REDUCED || typeof path.animate !== "function") return;
    const len = 120;
    path.style.strokeDasharray = String(len);
    const a = path.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }],
      { duration: 400, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" });
    return () => a.cancel();
  }, [c.from_token]);
  return (
    <span className="repair">
      <s ref={ref} aria-label={`suna: ${c.from_token}`}>
        {c.from_token}
        <svg viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true"><path d="M1 6 Q 25 3, 50 6 T 99 5" /></svg>
      </s>
      <b aria-label={`padha: ${c.to_surface}`}>{c.to_surface}</b>
      {c.asr_confidence != null && <small>{c.asr_confidence.toFixed(2)}</small>}
    </span>
  );
}

export function Register({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <div className="register-wrap" tabIndex={0} role="region" aria-label="Register — chhoti screen pe side mein scroll hota hai">
      <table className="register">
        <thead><tr>{head}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

/** The props that make a table row behave like a button: a role, a tab stop,
 *  and Enter or Space to activate — not just a mouse click. */
export function rowButton(activate: () => void, label?: string) {
  return {
    role: "button" as const,
    tabIndex: 0,
    "aria-label": label,
    className: "click",
    onClick: activate,
    onKeyDown: (e: KeyboardEvent<HTMLElement>) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); }
    },
  };
}

/** An inline "are you sure?" that stays where the action was asked. */
export function Confirm({ text, yes = "Haan", no = "Nahi", busy = false, onYes, onNo }:
  { text: string; yes?: string; no?: string; busy?: boolean; onYes: () => void; onNo: () => void }) {
  return (
    <div className="confirm" role="alertdialog" aria-label={text}>
      <span>{text}</span>
      <span className="row">
        <button className="btn btn-danger btn-sm" onClick={onYes} disabled={busy}>{busy ? "…" : yes}</button>
        <button className="btn btn-ghost btn-sm" onClick={onNo} disabled={busy}>{no}</button>
      </span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) { return <div className="empty">{children}</div>; }
export function Loading() { return <div className="loading">Loading…</div>; }

/**
 * Load something whenever `deps` change (and on `reload()`). `load` may be
 * null while the source is not ready yet — the hook then simply waits. The
 * previous data stays on screen while the next load is in flight; an error
 * only shows for the request that produced it. `deps` are primitives.
 */
export function useData<T>(load: (() => Promise<T>) | null, deps: unknown[]) {
  const [tick, setTick] = useState(0);
  const key = `${deps.map(String).join("\u0001")}\u0002${tick}\u0002${load ? 1 : 0}`;
  const [result, setResult] = useState<{ key: string; data?: T; error?: string } | null>(null);
  const loadRef = useRef(load);
  useEffect(() => { loadRef.current = load; });
  useEffect(() => {
    const run = loadRef.current;
    if (!run) return;
    let alive = true;
    run().then((data) => { if (alive) setResult({ key, data }); })
      .catch((e: Error) => { if (alive) setResult((r) => ({ key, data: r?.data, error: e.message })); });
    return () => { alive = false; };
  }, [key]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  const current = result?.key === key;
  return { data: result?.data, error: current ? result?.error : undefined, loading: !current, reload };
}

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso.slice(11, 16) : d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
}
export function fmtDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso.slice(0, 10) : d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
export function fmtInr(n: number): string { return "₹" + Math.round(n).toLocaleString("en-IN"); }


/** Where a turn's time went: one bar per span, to scale, speculated tools
 *  hatched because they cost the caller nothing. */
export function Waterfall({ spans, total }: { spans: { name: string; ms: number; speculated?: boolean; ok?: boolean; detail?: string }[]; total?: number | null }) {
  const sum = Math.max(total ?? 0, spans.reduce((a, s) => a + (s.speculated ? 0 : s.ms), 0), 1);
  let acc = 0;
  return (
    <div className="waterfall" role="img" aria-label={spans.map((s) => `${s.name} ${Math.round(s.ms)} ms`).join(", ")}>
      {spans.map((s, i) => {
        const left = acc;
        if (!s.speculated) acc += s.ms;
        const w = Math.max(0.6, (s.ms / sum) * 100);
        return (
          <div key={i} className="wf-row">
            <span className="wf-name mono">{s.name.replace("tool:", "")}{s.speculated ? " ⚡" : ""}</span>
            <span className="wf-track"><i className={"wf-bar" + (s.speculated ? " spec" : "") + (s.ok === false ? " bad" : "")} style={{ left: `${(left / sum) * 100}%`, width: `${w}%` }} /></span>
            <span className="wf-ms mono">{Math.round(s.ms)} ms{s.detail ? ` · ${s.detail}` : ""}</span>
          </div>
        );
      })}
    </div>
  );
}


/** Devanagari reading aid: the engine transliterates the given lines when
 *  the toggle is on; the result is approximate and labelled so. */
export function useDevanagari(lines: string[]): { on: boolean; toggle: () => void; map: (s: string) => string } {
  const [on, setOn] = useState<boolean>(devanagariWanted);
  const [table, setTable] = useState<Record<string, string>>({});
  const key = lines.join("\u0001");
  useEffect(() => {
    if (!on) return;
    const wanted = key ? key.split("\u0001") : [];
    let cancelled = false;
    // Ask for the lines not translated yet; the updater sees the latest table.
    setTable((t) => {
      const missing = wanted.filter((l) => l && !(l in t));
      if (missing.length) {
        engine.devanagari(missing).then((r) => {
          if (cancelled) return;
          setTable((cur) => { const n = { ...cur }; missing.forEach((l, i) => { n[l] = r.texts[i] ?? l; }); return n; });
        }).catch(() => { /* engine away: show Roman */ });
      }
      return t;
    });
    return () => { cancelled = true; };
  }, [on, key]);
  const toggle = () => { setDevanagariWanted(!on); setOn(!on); };
  return { on, toggle, map: (s: string) => (on ? table[s] ?? s : s) };
}

export function DevToggle({ on, toggle }: { on: boolean; toggle: () => void }) {
  return (
    <button className={"btn btn-ghost btn-sm dev-toggle" + (on ? " on" : "")} onClick={toggle} aria-pressed={on}
            title="Transcript Devanagari mein dikhao (approximate)">
      <span className="dev">हिंदी</span>{on ? " on" : ""}
    </button>
  );
}
