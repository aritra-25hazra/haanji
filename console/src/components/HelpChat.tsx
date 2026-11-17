import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { engine, type HelpProvider } from "../engine";
import { en, getLang, t, useT } from "../i18n";
import { Icon } from "./Common";

interface Msg { role: "user" | "assistant"; content: string; by?: HelpProvider }
const NAME: Record<HelpProvider, string> = { claude: "Claude", gemini: "Gemini", faq: en("Quick answers") };
const STARTERS = [en("How does a booking work?"), en("What is sample mode?"), en("How do I add a new shop?")];

/** A help assistant in the corner of every page. It answers questions about
 *  HaanJi and the console (Claude or Gemini when the engine has their keys,
 *  quick built-in answers otherwise); it never sees the shop's data. */
export function HelpChat() {
  useT();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [providers, setProviders] = useState<HelpProvider[] | null>(null);
  const [provider, setProvider] = useState<HelpProvider>("faq");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open || providers) return;
    engine.helpStatus().then((s) => { setProviders(s.providers); setProvider(s.providers[0] ?? "faq"); })
      .catch(() => setProviders(["faq"]));
  }, [open, providers]);
  useEffect(() => { if (open) input.current?.focus(); }, [open]);
  useEffect(() => { list.current?.scrollTo?.({ top: list.current.scrollHeight }); }, [msgs, busy]);

  async function send(q: string) {
    const question = q.trim();
    if (!question || busy) return;
    const next: Msg[] = [...msgs, { role: "user", content: question }];
    setMsgs(next); setText(""); setBusy(true); setError(null);
    try {
      const r = await engine.helpChat({ messages: next.map(({ role, content }) => ({ role, content })), provider, lang: getLang(), page: pathname });
      setMsgs([...next, { role: "assistant", content: r.reply, by: r.provider }]);
    } catch (e) {
      setError((e as Error).message || t("The help assistant needs the engine, which may be waking up. Try again in a minute."));
    } finally { setBusy(false); }
  }
  const close = () => { setOpen(false); button.current?.focus(); };

  return (
    <>
      <button ref={button} type="button" className="help-fab" aria-expanded={open} aria-controls="help-chat" onClick={() => (open ? close() : setOpen(true))}>
        <span aria-hidden="true">?</span>{t("Help")}
      </button>
      {open && (
        <section id="help-chat" className="help-chat" role="dialog" aria-label={t("Help assistant")} onKeyDown={(e) => { if (e.key === "Escape") close(); }}>
          <header>
            <div>
              <h2>{t("Help assistant")}</h2>
              <p className="muted small">{t("Answers about HaanJi and this console. It cannot see your shop's data.")}</p>
            </div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={close} aria-label={t("Close help")}><Icon name="x" small /></button>
          </header>
          <div className="help-pick" role="radiogroup" aria-label={t("Who answers")}>
            {(["claude", "gemini", "faq"] as HelpProvider[]).map((p) => {
              const on = providers?.includes(p) ?? p === "faq";
              return (
                <button key={p} type="button" role="radio" aria-checked={provider === p} disabled={!on}
                        title={on ? undefined : t("Switches on when the engine has a {name} key", { name: NAME[p] })}
                        onClick={() => setProvider(p)}>{p === "faq" ? t(NAME[p]) : NAME[p]}</button>
              );
            })}
          </div>
          <div className="help-log" ref={list} aria-live="polite">
            {msgs.length === 0 && (
              <div className="help-starters">
                {STARTERS.map((s) => <button key={s} type="button" className="btn btn-ghost btn-sm" onClick={() => void send(t(s))}>{t(s)}</button>)}
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={"help-msg " + m.role}>
                <p>{m.content}</p>
                {m.by && <small className="muted">{m.by === "faq" ? t(NAME.faq) : NAME[m.by]}</small>}
              </div>
            ))}
            {busy && <div className="help-msg assistant"><p className="muted">{t("Thinking…")}</p></div>}
            {error && <p className="help-error" role="alert">{error}</p>}
          </div>
          <form className="help-form" onSubmit={(e) => { e.preventDefault(); void send(text); }}>
            <label className="sr-only" htmlFor="help-q">{t("Your question")}</label>
            <textarea id="help-q" ref={input} rows={2} maxLength={1200} value={text} placeholder={t("Ask in English or Hinglish…")}
                      onChange={(e) => setText(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(text); } }} />
            <button className="btn btn-primary btn-sm" type="submit" disabled={busy || !text.trim()}>{t("Send")}</button>
          </form>
        </section>
      )}
    </>
  );
}
