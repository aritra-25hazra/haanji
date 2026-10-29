import { describe, expect, it } from "vitest";
import { enginePath, errorMessage, fmtMs, parseReceipts, parseTurns, tamper } from "./engine";
import type { Export } from "./types";

describe("enginePath", () => {
  it("prefixes with /engine and strips leading slashes", () => {
    expect(enginePath("api/status")).toBe("/engine/api/status");
    expect(enginePath("/api/status")).toBe("/engine/api/status");
  });
});

describe("errorMessage", () => {
  it("replaces a proxy's HTML error page with a plain sentence", () => {
    expect(errorMessage(502, "text/html", "<html><body><h1>502 Bad Gateway</h1></body></html>")).toBe("Engine jawab nahi de raha (502)");
    expect(errorMessage(503, null, "<!DOCTYPE html><html><head></head><body>Service Unavailable</body></html>")).toBe("Engine jawab nahi de raha (503)");
  });
  it("surfaces the engine's own detail", () => {
    expect(errorMessage(422, "application/json", JSON.stringify({ detail: "unknown setting: foo" }))).toBe("unknown setting: foo");
    expect(errorMessage(422, "application/json", JSON.stringify({ detail: [{ loc: ["body", "phone"], msg: "field required" }] }))).toBe("field required");
    expect(errorMessage(500, "text/plain", "boom")).toBe("boom");
    expect(errorMessage(500, null, "")).toBe("Engine error 500");
  });
});

describe("parseTurns", () => {
  it("returns normalised turns", () => {
    const turns = parseTurns(JSON.stringify([{ heard: "rut kanal", said: "Theek hai." }]));
    expect(turns).toHaveLength(1);
    expect(turns[0]).toMatchObject({ heard: "rut kanal", corrected: "rut kanal", said: "Theek hai.",
      tools: [], speculation_hits: [], guard: null, latency_ms: null, interrupted: false, corrections: [] });
  });
  it("is empty for malformed or missing json", () => {
    expect(parseTurns("not json")).toEqual([]);
    expect(parseTurns(null)).toEqual([]);
    expect(parseTurns('{"a":1}')).toEqual([]);
  });
});

describe("parseReceipts", () => {
  it("reads a list of codes and tolerates garbage", () => {
    expect(parseReceipts('["2504-7863"]')).toEqual(["2504-7863"]);
    expect(parseReceipts("")).toEqual([]);
    expect(parseReceipts("{")).toEqual([]);
  });
});

describe("fmtMs", () => {
  it("formats sub-millisecond, normal and missing latencies", () => {
    expect(fmtMs(0.4)).toBe("<1 ms");
    expect(fmtMs(22.4)).toBe("22 ms");
    expect(fmtMs(null)).toBe("—");
  });
});

describe("tamper", () => {
  it("edits one field of the middle receipt and leaves the original alone", () => {
    const exp: Export = { tenant_id: "t", algorithm: "Ed25519", public_key: "", exported_at: "",
      receipts: [1, 2, 3].map((seq) => ({ seq, action: "book_appointment", action_args: JSON.stringify({ time: "09:30" }) })) };
    const { edited, seq } = tamper(exp);
    expect(seq).toBe(2);
    expect(JSON.parse(edited.receipts[1]!.action_args).time).toBe("18:00");
    expect(JSON.parse(exp.receipts[1]!.action_args).time).toBe("09:30");
  });
});
