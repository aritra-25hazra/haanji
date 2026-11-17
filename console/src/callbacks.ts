import type { CallRow, Turn } from "./types";

/** Why a call needs the owner: the caller's line that caused the hand-off or
 *  the lead (not the first thing they said), a short reason, and whether it
 *  is urgent (a guardrail emergency). */
export function callbackWhy(c: CallRow): { ask: string; tag: string; urgent: boolean } {
  let turns: Turn[] = [];
  try { turns = JSON.parse(c.turns_json) as Turn[]; } catch { /* an unreadable call keeps the outcome as its reason */ }
  const trigger = [...turns].reverse().find((t) => t.guard || t.tools.some((x) => x === "handoff" || x === "capture_lead"))
    ?? turns[turns.length - 1];
  const ask = trigger?.corrected || trigger?.heard || "—";
  const guard = turns.find((t) => t.guard)?.guard ?? "";
  const text = turns.map((t) => t.corrected || t.heard).join(" ").toLowerCase();
  const urgent = guard.startsWith("emergency.");
  const tag = urgent ? "emergency"
    : guard === "commercial.complaint" ? "shikayat"
    : guard === "commercial.refund" ? "refund"
    : guard === "handoff.request" ? "staff se baat"
    : /insurance|claim/.test(text) ? "insurance"
    : /daam|price|rate|kitna|charge|discount/.test(text) ? "daam"
    : /sunday|ravivaar|somvaar|monday|band|der se|late/.test(text) ? "time / band din"
    : c.outcome === "HANDED_OFF" ? "staff se baat" : "callback";
  return { ask, tag, urgent };
}
