import { describe, expect, it } from "vitest";
import { readValidation } from "./decision";

describe("readValidation", () => {
  it("reads a full weighted validation result", () => {
    const result = readValidation({
      risk: "MEDIUM",
      constraints: "PASS",
      conflicts: ["c1"],
      warnings: ["w1", "w2"],
      score: 71.5,
      verdict: "RECOMMEND",
      score_breakdown: {
        risk: { weight: 0.15, value: 0.7, contribution: 10.5 },
        profit: { weight: 0.3, value: 0.6, contribution: 18 },
        custom_factor: { weight: 0.1, value: 1, contribution: 10 },
      },
    });
    expect(result.score).toBe(71.5);
    expect(result.verdict).toBe("RECOMMEND");
    expect(result.risk).toBe("MEDIUM");
    expect(result.constraints).toBe("PASS");
    expect(result.conflicts).toEqual(["c1"]);
    expect(result.warnings).toEqual(["w1", "w2"]);
    // Known factors come first in canonical order, unknown ones after.
    expect(result.breakdown.map((row) => row.key)).toEqual(["profit", "risk", "custom_factor"]);
    expect(result.breakdown[0].label).toBe("Profit");
    expect(result.breakdown[2].label).toBe("custom_factor");
  });

  it.each([null, undefined, "text", 5, [], {}])("copes with an old or empty result: %j", (raw) => {
    const result = readValidation(raw);
    expect(result.score).toBeNull();
    expect(result.verdict).toBeNull();
    expect(result.risk).toBeNull();
    expect(result.constraints).toBeNull();
    expect(result.conflicts).toEqual([]);
    expect(result.warnings).toEqual([]);
    expect(result.breakdown).toEqual([]);
  });

  it("ignores values of the wrong type", () => {
    const result = readValidation({
      score: "high",
      verdict: "MAYBE",
      risk: 3,
      constraints: false,
      conflicts: "nope",
      warnings: null,
      score_breakdown: "bad",
    });
    expect(result.score).toBeNull();
    expect(result.verdict).toBeNull();
    expect(result.risk).toBeNull();
    expect(result.constraints).toBeNull();
    expect(result.conflicts).toEqual([]);
    expect(result.warnings).toEqual([]);
    expect(result.breakdown).toEqual([]);
  });

  it("rejects non-finite scores", () => {
    expect(readValidation({ score: Number.NaN }).score).toBeNull();
  });

  it("skips malformed breakdown entries", () => {
    const result = readValidation({
      score_breakdown: {
        profit: null,
        risk: { weight: 0.1, value: "x", contribution: 1 },
        confidence: { weight: 0.2, value: 0.5, contribution: 10 },
      },
    });
    expect(result.breakdown.map((row) => row.key)).toEqual(["confidence"]);
  });

  it("treats an array score_breakdown as missing", () => {
    expect(readValidation({ score_breakdown: [1, 2] }).breakdown).toEqual([]);
  });

  it("stringifies non-string conflict entries", () => {
    expect(readValidation({ conflicts: [1, "b"] }).conflicts).toEqual(["1", "b"]);
  });
});
