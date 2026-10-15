import { describe, expect, it } from "vitest";
import {
  DASH,
  formatCompact,
  formatDateTime,
  formatDay,
  formatDuration,
  formatFraction,
  formatFuelPrice,
  formatNumber,
  formatPercent,
  formatRate,
  formatRelative,
  formatScore,
  formatSignedUsd,
  formatUsdValue,
  truncate,
} from "./format";

describe("format helpers render a dash for missing values", () => {
  it.each([null, undefined, Number.NaN, Number.POSITIVE_INFINITY])("for %s", (value) => {
    expect(formatUsdValue(value)).toBe(DASH);
    expect(formatSignedUsd(value)).toBe(DASH);
    expect(formatCompact(value)).toBe(DASH);
    expect(formatDuration(value)).toBe(DASH);
    expect(formatFraction(value)).toBe(DASH);
    expect(formatPercent(value)).toBe(DASH);
    expect(formatScore(value)).toBe(DASH);
    expect(formatNumber(value)).toBe(DASH);
    expect(formatFuelPrice(value)).toBe(DASH);
    expect(formatRate(value)).toBe(DASH);
  });
  it("for missing or invalid dates", () => {
    expect(formatDateTime(null)).toBe(DASH);
    expect(formatDateTime("not a date")).toBe(DASH);
    expect(formatRelative(null)).toBe(DASH);
    expect(formatRelative("nope")).toBe(DASH);
  });
});

describe("formatSignedUsd", () => {
  it("signs positive and negative amounts", () => {
    expect(formatSignedUsd(1200)).toBe("+$1,200");
    expect(formatSignedUsd(-300.4)).toBe("-$300");
  });
  it("shows zero without a sign, including values that round to zero", () => {
    expect(formatSignedUsd(0)).toBe("$0");
    expect(formatSignedUsd(0.2)).toBe("$0");
  });
});

describe("formatCompact", () => {
  it("abbreviates thousands, millions and billions", () => {
    expect(formatCompact(999)).toBe("999");
    expect(formatCompact(1500)).toBe("1.5K");
    expect(formatCompact(2_400_000)).toBe("2.4M");
    expect(formatCompact(3_100_000_000)).toBe("3.1B");
    expect(formatCompact(-1500)).toBe("-1.5K");
  });
});

describe("formatDuration", () => {
  it("covers ms, seconds and minutes", () => {
    expect(formatDuration(0)).toBe("0 ms");
    expect(formatDuration(850)).toBe("850 ms");
    expect(formatDuration(12_400)).toBe("12.4 s");
    expect(formatDuration(125_000)).toBe("2m 05s");
  });
  it("carries a rounded-up 60 seconds into the minutes", () => {
    expect(formatDuration(119_700)).toBe("2m 00s");
  });
  it("rejects negative durations", () => {
    expect(formatDuration(-5)).toBe(DASH);
  });
});

describe("simple numeric formatters", () => {
  it("format fractions, percentages, scores, numbers, fuel and rates", () => {
    expect(formatFraction(0.824)).toBe("82%");
    expect(formatPercent(12.345)).toBe("12.3%");
    expect(formatPercent(12.345, 0)).toBe("12%");
    expect(formatScore(71.6)).toBe("72");
    expect(formatNumber(1234567)).toBe("1,234,567");
    expect(formatFuelPrice(2.3456)).toBe("$2.35/gal");
    expect(formatRate(83.456)).toBe("83.46");
    expect(formatUsdValue(85000)).toBe("$85,000");
  });
});

describe("dates", () => {
  it("formatDateTime renders day, month and time", () => {
    expect(formatDateTime("2026-10-15T14:03:00Z")).toMatch(/\d{2} \w{3},? \d{2}:\d{2}/);
  });
  it("formatRelative buckets by age", () => {
    const now = new Date("2026-10-15T12:00:00Z");
    expect(formatRelative("2026-10-15T11:59:40Z", now)).toBe("just now");
    expect(formatRelative("2026-10-15T11:30:00Z", now)).toBe("30m ago");
    expect(formatRelative("2026-10-15T07:00:00Z", now)).toBe("5h ago");
    expect(formatRelative("2026-10-10T12:00:00Z", now)).toBe("5d ago");
  });
  it("formatRelative clamps timestamps in the future", () => {
    expect(formatRelative("2026-10-15T13:00:00Z", new Date("2026-10-15T12:00:00Z"))).toBe("just now");
  });
  it("formatDay renders a short date and passes junk through", () => {
    expect(formatDay("2026-10-15")).toBe("15 Oct");
    expect(formatDay("garbage")).toBe("garbage");
  });
});

describe("truncate", () => {
  it("leaves short text and truncates long text with an ellipsis", () => {
    expect(truncate("short", 10)).toBe("short");
    expect(truncate("a".repeat(500), 20)).toHaveLength(20);
    expect(truncate("a".repeat(500), 20).endsWith("…")).toBe(true);
  });
  it("copes with a zero limit", () => {
    expect(truncate("abc", 0)).toBe("…");
  });
});
