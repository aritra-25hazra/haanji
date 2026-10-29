import { describe, expect, it } from "vitest";
import { addDays, eachDay, fmtDay, isoDay, parseDay, weekOf } from "./dates";

describe("dates", () => {
  it("round-trips a day in local time", () => {
    expect(isoDay(parseDay("2026-10-29"))).toBe("2026-10-29");
    expect(isoDay(new Date(2026, 0, 5))).toBe("2026-01-05");
  });
  it("adds days across month ends", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });
  it("builds Monday-first weeks", () => {
    // 2026-10-29 is a Thursday.
    expect(weekOf("2026-10-29")).toEqual(["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01"]);
    expect(weekOf("2026-11-01")[0]).toBe("2026-10-26");
  });
  it("lists every day of a range inclusive", () => {
    expect(eachDay("2026-02-27", "2026-03-02")).toEqual(["2026-02-27", "2026-02-28", "2026-03-01", "2026-03-02"]);
    expect(eachDay("2026-03-02", "2026-03-01")).toEqual([]);
  });
  it("names the day", () => {
    expect(fmtDay("2026-10-29")).toBe("Guru 29 Oct");
  });
});
