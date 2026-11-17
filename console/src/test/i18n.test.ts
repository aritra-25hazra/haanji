import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { HI } from "../hi";
import { getLang, setLang, t } from "../i18n";

// Every English string a screen passes to t() or marks with en() has Hindi,
// and keeps the same {placeholders}. Read straight from the source files.
const SRC = join(__dirname, "..");
const files = (dir: string): string[] => readdirSync(dir).flatMap((f) => {
  const p = join(dir, f);
  if (statSync(p).isDirectory()) return f === "test" || f === "hi" ? [] : files(p);
  return /\.(tsx?|ts)$/.test(f) && !/\.test\./.test(f) ? [p] : [];
});
const CALL = /\b(?:t|en)\(\s*("(?:[^"\\]|\\.)*")/g;
const used = new Map<string, string>();
for (const f of files(SRC)) {
  const src = readFileSync(f, "utf8");
  for (const m of src.matchAll(CALL)) used.set(JSON.parse(m[1]!) as string, f.slice(SRC.length + 1));
}
const holes = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("the Hindi dictionary", () => {
  it("finds the console's strings", () => { expect(used.size).toBeGreaterThan(20); });
  it.each([...used.entries()])("has Hindi for %j (%s)", (s) => {
    expect(HI[s], `no Hindi for ${JSON.stringify(s)}`).toBeTruthy();
    expect(holes(HI[s]!)).toEqual(holes(s));
  });
});

describe("t()", () => {
  it("is English by default, Hindi when switched, and fills placeholders in both", () => {
    const was = getLang();
    setLang("en");
    expect(t("Calls")).toBe("Calls");
    setLang("hi");
    expect(t("Try again")).toBe(HI["Try again"]);
    expect(t("{n} calls", { n: 3 })).toBe((HI["{n} calls"] ?? "{n} calls").replace("{n}", "3"));
    setLang(was);
  });
});
