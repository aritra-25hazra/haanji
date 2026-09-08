import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { isOffline } from "../api";

export function Page({ title, sub, children }:
  { title: string; sub?: string; children: ReactNode }) {
  return (
    <>
      <h1 className="page-title">{title}</h1>
      {sub && <p className="page-sub">{sub}</p>}
      {isOffline() && (
        <div className="banner">
          Panels without a ● live mark show the sample dataset; anything marked
          ● live is real, straight from the engine server on this machine.
        </div>
      )}
      {children}
    </>
  );
}

export function Panel({ title, hint, children }:
  { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="panel">
      <header><h2>{title}</h2>{hint && <span className="hint">{hint}</span>}</header>
      {children}
    </section>
  );
}

export function Stat({ label, value, foot }:
  { label: string; value: ReactNode; foot?: string }) {
  return (
    <div className="card">
      <h3>{label}</h3>
      <div className="value">{value}</div>
      {foot && <div className="foot">{foot}</div>}
    </div>
  );
}

export function Badge({ kind }: { kind: string }) {
  return <span className={`badge ${kind}`}>{kind.replace(/_/g, " ").toLowerCase()}</span>;
}

/** Small data hook. No cache and no library: five screens do not need one, and
 *  the loading and error states stay visible in one place. */
export function useData<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>(
    { loading: true },
  );
  useEffect(() => {
    let alive = true;
    setState({ loading: true });
    load()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((e: Error) => alive && setState({ error: e.message, loading: false }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export function fmtDuration(ms: number): string {
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-IN",
    { hour: "2-digit", minute: "2-digit", hour12: false });
}
