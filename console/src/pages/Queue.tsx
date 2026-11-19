import { useEffect, useState, type FormEvent } from "react";
import { engine, enginePath } from "../engine";
import { sample } from "../sample";
import { useApp } from "../state";
import { t, tn, useT } from "../i18n";
import { Chip, Empty, Icon, Loading, NotLive, Page, Panel, Register, fmtDate, useData } from "../components/Common";
import type { QueueLine, QueueToken, QueueView } from "../types";

/**
 * Reception's queue for today: check in the booked patients as they arrive,
 * give walk-ins a token, call the next token for each doctor, mark a no-show.
 * The waiting-room screen (/queue on the engine) shows the same lines by
 * token only. Refreshes every 5 seconds.
 */
export default function Queue() {
  const { pack, mode, readOnly } = useApp();
  useT();
  const live = mode === "live";
  const demo = mode === "demo";
  const { data, loading, error, reload } = useData<QueueView>(
    live ? () => engine.queue(pack) : demo ? () => Promise.resolve(sample.queue(pack)) : null, [pack, mode]);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!live) return;
    const id = setInterval(reload, 5000);
    return () => clearInterval(id);
  }, [live, reload]);

  const screen = enginePath(`queue?pack=${encodeURIComponent(pack)}`);
  if (!live && !demo) return <NotLive title={t("Queue")} sub={t("Today's tokens, doctor by doctor.")} kind="staff" />;

  const run = async (key: string, fn: () => Promise<string>) => {
    if (!live) { setNote(t("This is a sample queue; nothing changes here. Sign in to the live console to call real tokens.")); return; }
    setBusy(key); setNote(null);
    try { setNote(await fn()); reload(); }
    catch (e) { setNote(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };
  const checkIn = (id: string, name: string | null) => run(id, async () => {
    const tok = await engine.queueCheckIn(pack, id);
    return t("Checked in · {name} has token {label}.", { name: name ?? "—", label: tok.label });
  });
  const next = (line: QueueLine) => run(line.staff, async () => {
    const out = await engine.queueNext(pack, line.staff);
    return out.serving ? t("{doctor}: now seeing {label}.", { doctor: line.staff, label: out.serving.label })
      : t("{doctor}: nobody is waiting.", { doctor: line.staff });
  });
  const noShow = (tok: QueueToken) => run(tok.token_id, async () => {
    await engine.queueMark(pack, tok.token_id, "no_show");
    return t("{label} marked as a no-show.", { label: tok.label });
  });

  const lines = data?.lines ?? [];
  const departments = [...new Set(lines.map((l) => l.department ?? ""))];
  const waiting = lines.reduce((n, l) => n + l.waiting.length, 0);

  return (
    <Page title={t("Queue")} sub={t("Today's tokens, doctor by doctor.")}
          actions={<a className="btn btn-ghost" href={screen} target="_blank" rel="noopener noreferrer"><Icon name="external" small />{t("Waiting-room screen")}</a>}>
      {note && <div className="banner" role="status"><Icon name="check" small />{note}</div>}
      {data?.as_of && <p className="muted">{t("It is closed now, so the sample shows the queue at {time} on {day}.", { time: data.as_of.time, day: fmtDate(data.as_of.day) })}</p>}
      {loading && !data ? <Loading kind="staff" /> : error && !data ? (
        <Empty>{t("Could not load: {error}", { error })}<button className="btn btn-ghost btn-sm" onClick={reload}>{t("Try again")}</button></Empty>
      ) : (
        <>
          <Panel title={t("To check in")} hint={data ? tn("{n} booked patient not here yet", "{n} booked patients not here yet", data.to_check_in.length) : ""}>
            {!data || data.to_check_in.length === 0 ? (
              <Empty><p>{t("Everyone booked for today has checked in.")}</p></Empty>
            ) : (
              <Register cards head={<><th>{t("Time")}</th><th>{t("Name")}</th><th>{t("Doctor")}</th><th>{t("Service")}</th><th></th></>}>
                {data.to_check_in.map((b) => (
                  <tr key={b.booking_id}>
                    <td className="mono">{b.time}</td>
                    <td><strong>{b.customer_name || "—"}</strong></td>
                    <td>{b.staff}</td>
                    <td>{b.service}</td>
                    <td className="right">
                      <button className="btn btn-primary btn-sm" disabled={readOnly || busy === b.booking_id}
                              onClick={() => void checkIn(b.booking_id, b.customer_name)}>{t("Check in")}</button>
                    </td>
                  </tr>
                ))}
              </Register>
            )}
          </Panel>

          <WalkIn lines={lines} disabled={readOnly} onDone={(msg) => { setNote(msg); reload(); }} />

          <Panel title={t("Lines")} hint={tn("{n} waiting", "{n} waiting", waiting)}>
            {departments.map((dept) => (
              <section key={dept} className="q-dept">
                {dept && <h3 className="q-dept-name">{dept}</h3>}
                <div className="q-grid">
                  {lines.filter((l) => (l.department ?? "") === dept).map((l) => (
                    <article key={l.staff} className="q-line" data-testid={`line-${l.staff}`}>
                      <div className="q-head"><b>{l.staff}</b><span className="muted small">{t("about {n} min each", { n: Math.round(l.avg_minutes) })}</span></div>
                      <div className={"q-now" + (l.serving ? "" : " idle")}>{l.serving ? l.serving.label : "—"}</div>
                      {l.serving && <p className="small">{t("Now seeing")}: {l.serving.name || t("walk-in")}</p>}
                      <ol className="q-waiting">
                        {l.waiting.map((w) => (
                          <li key={w.token_id}><span className="mono">{w.label}</span> {w.name || "—"}
                            {w.kind === "walkin" && <Chip kind="muted">{t("walk-in")}</Chip>}</li>
                        ))}
                      </ol>
                      <div className="acts">
                        <button className="btn btn-primary btn-sm" disabled={readOnly || busy === l.staff || (!l.serving && l.waiting.length === 0)}
                                onClick={() => void next(l)}>{t("Next patient")}</button>
                        {l.serving && <button className="btn btn-ghost btn-sm" disabled={readOnly || busy === l.serving.token_id}
                                              onClick={() => void noShow(l.serving!)}>{t("No-show")}</button>}
                      </div>
                      <p className="muted small">{t("{done} seen · {absent} no-show", { done: l.done, absent: l.no_show })}</p>
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </Panel>
        </>
      )}
    </Page>
  );
}

/** A walk-in gets a token for the doctor the desk picks. */
function WalkIn({ lines, disabled, onDone }: { lines: QueueLine[]; disabled: boolean; onDone: (msg: string) => void }) {
  const { pack } = useApp();
  useT();
  const [staff, setStaff] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const tok = await engine.queueWalkIn(pack, { staff: staff || lines[0]?.staff, name: name || undefined, phone: phone || undefined });
      onDone(t("Walk-in · token {label} for {doctor}.", { label: tok.label, doctor: tok.staff }));
      setName(""); setPhone("");
    } catch (x) { setErr(x instanceof Error ? x.message : String(x)); }
    finally { setBusy(false); }
  };
  return (
    <Panel title={t("Walk-in")}>
      <form className="q-walkin" onSubmit={(e) => void submit(e)}>
        <label className="field"><span>{t("Doctor")}</span>
          <select className="input" value={staff} onChange={(e) => setStaff(e.target.value)}>
            {lines.map((l) => <option key={l.staff} value={l.staff}>{l.staff}{l.department ? ` · ${l.department}` : ""} ({l.waiting.length})</option>)}
          </select>
        </label>
        <label className="field"><span>{t("Name")}</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="field"><span>{t("Phone (optional)")}</span><input className="input" inputMode="numeric" value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
        <button className="btn btn-primary" type="submit" disabled={disabled || busy || lines.length === 0}>{t("Give a token")}</button>
      </form>
      {err && <p className="muted" role="alert" style={{ padding: "0 18px 12px" }}>{err}</p>}
    </Panel>
  );
}
