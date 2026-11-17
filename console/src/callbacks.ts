import { t } from "./i18n";
import type { CallRow, Turn } from "./types";

/** Why a call needs the owner: the caller's line that caused the hand-off or
 *  the lead (not the first thing they said), a short reason, and whether it
 *  is urgent (a guardrail emergency). */
export function callbackWhy(c: CallRow): { ask: string; tag: string; urgent: boolean } {
  let turns: Turn[] = [];
  try { turns = JSON.parse(c.turns_json) as Turn[]; } catch { /* an unreadable call keeps the outcome as its reason */ }
  const trigger = [...turns].reverse().find((x) => x.guard || x.tools.some((n) => n === "handoff" || n === "capture_lead"))
    ?? turns[turns.length - 1];
  const ask = trigger?.corrected || trigger?.heard || "—";
  const guard = turns.find((x) => x.guard)?.guard ?? "";
  const text = turns.map((x) => x.corrected || x.heard).join(" ").toLowerCase();
  const urgent = guard.startsWith("emergency.");
  const tag = urgent ? t("emergency")
    : guard === "commercial.complaint" ? t("complaint")
    : guard === "commercial.refund" ? t("refund")
    : guard === "handoff.request" ? t("wants staff")
    : /insurance|claim/.test(text) ? t("insurance")
    : /daam|price|rate|kitna|charge|discount/.test(text) ? t("price")
    : /sunday|ravivaar|somvaar|monday|band|der se|late/.test(text) ? t("timing / closed day")
    : c.outcome === "HANDED_OFF" ? t("wants staff") : t("callback");
  return { ask, tag, urgent };
}
