import { LANGS, setLang, t, useLang } from "../i18n";
import { useApp } from "../state";

/** Who answers the calls, said plainly: the built-in rules (the default, and
 *  what the sample shop uses), or a hosted model named by its provider. */
export function AiChip() {
  const { status, sampleView } = useApp();
  useLang();
  const d = sampleView || !status ? { provider: "rules" } : status.dialogue ?? { provider: "rules" };
  const label = d.provider === "gemini" ? t("AI: Gemini") : d.provider === "claude" ? t("AI: Claude") : t("AI: built-in rules");
  const title = d.provider === "rules"
    ? t("Calls are answered by HaanJi's own rules for this kind of shop: speech recognition, then rules that ask, check and book. No outside AI service is used.")
    : t("Calls are answered by a hosted AI model; every booking still needs the caller's yes, checked by HaanJi's own rules.");
  return <span className="ai-chip" title={title}>{label}{sampleView ? ` · ${t("sample")}` : ""}</span>;
}

/** English or Hindi for every screen; remembered per browser, `?lang=hi` in a link. */
export function LangSwitch() {
  const lang = useLang();
  return (
    <div className="lang-switch" role="group" aria-label="Language / भाषा">
      {LANGS.map((l) => (
        <button key={l.id} type="button" aria-pressed={lang === l.id} title={l.label} lang={l.id === "hi" ? "hi" : "en"}
                onClick={() => setLang(l.id)}>{l.short}</button>
      ))}
    </div>
  );
}
