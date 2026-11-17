import { describe, expect, it } from "vitest";
import { callbackWhy } from "../callbacks";
import { NEEDS_CALLBACK, sample } from "../sample";
import type { CallRow, Turn } from "../types";

const t = (heard: string, extra: Partial<Turn> = {}): Turn =>
  ({ heard, corrected: heard, said: "", tools: [], speculation_hits: [], guard: null, latency_ms: 1, interrupted: false, corrections: [], ...extra });
const row = (outcome: string, turns: Turn[]): CallRow => ({ call_id: "c", channel: "PHONE", phone: null, started_at: "2026-11-17T15:00:00+00:00",
  outcome, corrections: 0, spec_hits: 0, latency_p50: 1, turns_json: JSON.stringify(turns), receipts_json: "[]" });

describe("why a call is on the callback list", () => {
  it("quotes the line that caused the hand-off, not the first line, and marks an emergency urgent", () => {
    const why = callbackWhy(row("HANDED_OFF", [t("akal daad nikalwani thi"), t("khoon ruk nahi raha", { tools: ["handoff"], guard: "emergency.bleeding" })]));
    expect(why).toEqual({ ask: "khoon ruk nahi raha", tag: "emergency", urgent: true });
  });
  it("tags a lead by what it was about", () => {
    expect(callbackWhy(row("LEAD_CAPTURED", [t("insurance claim ke baare mein poochna tha"), t("naam Ravi", { tools: ["capture_lead"] })])).tag).toBe("insurance");
    expect(callbackWhy(row("LEAD_CAPTURED", [t("Ravivaar ko slot milega kya", { tools: ["capture_lead"] })])).tag).toBe("time / band din");
  });
  it("finds an urgent sample call in a pack whose day has emergencies", () => {
    const calls = sample.calls("dental_clinic").filter(NEEDS_CALLBACK);
    for (const c of calls) expect(callbackWhy(c).ask).not.toBe("—");
  });
});
