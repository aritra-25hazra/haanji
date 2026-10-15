import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { useApp } from "../state";

const REDUCED = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

// ── icons: one family, inline SVG ──────────────────────────────────────────
const PATHS: Record<string, string> = {
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6.2 6.2l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
  mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/>',
  bolt: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  arrow: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  chevron: '<polyline points="6 9 12 15 18 9"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.5 15a9 9 0 1 1-2.1-9.4L23 10"/>',
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
  const { checked, online } = useApp();
  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">{title}</h1>
          {sub && <p className="page-sub">{sub}</p>}
        </div>
        {actions && <div className="row">{actions}</div>}
      </div>
      {checked && !online && (
        <div className="banner" role="status">
          <Icon name="refresh" small />
          Engine se connect nahi ho pa raha — sample data dikha raha hoon. Thodi der mein dobara try karo.
        </div>
      )}
      {children}
    </>
  );
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
  const [n, setN] = useState(REDUCED ? target : 0);
  const from = useRef(0);
  useEffect(() => {
    if (REDUCED) { setN(target); return; }
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
  return n;
}

function CountUp({ value, decimals }: { value: number; decimals: number }) {
  const n = useCountUp(value);
  return <>{n.toLocaleString("en-IN", { maximumFractionDigits: decimals, minimumFractionDigits: decimals })}</>;
}

export function Tile({ label, value, foot, mono = false, decimals = 0, prefix = "", suffix = "", index = 0 }:
  { label: string; value: ReactNode | number; foot?: string; mono?: boolean; decimals?: number; prefix?: string; suffix?: string; index?: number }) {
  return (
    <div className="tile" data-reveal style={{ "--i": index } as CSSProperties}>
      <h3>{label}</h3>
      <div className={"value" + (mono ? " mono" : "")}>
        {typeof value === "number" ? <>{prefix}<CountUp value={value} decimals={decimals} />{suffix}</> : value}
      </div>
      {foot && <div className="foot">{foot}</div>}
    </div>
  );
}

export function Chip({ kind, mono = false, children }:
  { kind?: "ok" | "warn" | "bad" | "muted"; mono?: boolean; children: ReactNode }) {
  return <span className={"chip" + (kind ? ` ${kind}` : "") + (mono ? " mono" : "")}>{children}</span>;
}

const OUTCOME_KIND: Record<string, "ok" | "warn" | "bad" | "muted" | undefined> = {
  BOOKED: "ok", FAQ_ANSWERED: undefined, LEAD_CAPTURED: "warn", HANDED_OFF: "bad", ABANDONED: "muted", IN_PROGRESS: "muted",
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
    if (!el || REDUCED) return;
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
  const [painted, setPainted] = useState(REDUCED);
  useEffect(() => {
    const s = ref.current;
    if (!s) return;
    const path = s.querySelector("path");
    if (!path || REDUCED) { setPainted(true); return; }
    const len = 120;
    path.style.strokeDasharray = String(len);
    const a = path.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }],
      { duration: 400, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" });
    setPainted(true);
    return () => a.cancel();
  }, [c.from_token]);
  return (
    <span className={"repair" + (painted ? " in" : "")}>
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
    <div className="register-wrap">
      <table className="register">
        <thead><tr>{head}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) { return <div className="empty">{children}</div>; }
export function Loading() { return <div className="loading">Loading…</div>; }

export function useData<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: s.data === undefined }));
    load().then((data) => alive && setState({ data, loading: false }))
      .catch((e: Error) => alive && setState((s) => ({ ...s, error: e.message, loading: false })));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
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
