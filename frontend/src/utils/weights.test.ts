import { describe, expect, it } from "vitest";
import type { DecisionWeights } from "../types/api";
import { AGENT_KEYS, DEFAULT_WEIGHTS, normalizeGroup, toWeightsPayload, validateWeights, weightsEqual } from "./weights";

function weights(patch: Partial<DecisionWeights> = {}): DecisionWeights {
  return structuredClone({ ...DEFAULT_WEIGHTS, ...patch });
}

describe("normalizeGroup", () => {
  it("turns weights into shares that sum to 1", () => {
    const shares = normalizeGroup({ a: 1, b: 3 });
    expect(shares).toEqual({ a: 0.25, b: 0.75 });
  });
  it("returns zero shares when every weight is zero", () => {
    expect(normalizeGroup({ a: 0, b: 0 })).toEqual({ a: 0, b: 0 });
  });
  it("treats negative and non-finite values as zero", () => {
    expect(normalizeGroup({ a: -5, b: Number.NaN, c: 2 })).toEqual({ a: 0, b: 0, c: 1 });
  });
  it("the default factor shares already sum to 1", () => {
    const total = Object.values(normalizeGroup(DEFAULT_WEIGHTS.factors)).reduce((s, v) => s + v, 0);
    expect(total).toBeCloseTo(1);
  });
});

describe("validateWeights", () => {
  it("accepts the defaults", () => expect(validateWeights(DEFAULT_WEIGHTS)).toEqual([]));

  it("rejects negative weights in either group", () => {
    const w = weights();
    w.factors.profit = -0.1;
    w.agent_confidence.CREW = -1;
    const errors = validateWeights(w);
    expect(errors).toContain("Factor weights: weights cannot be negative.");
    expect(errors).toContain("Agent confidence weights: weights cannot be negative.");
  });

  it("rejects all-zero groups", () => {
    const w = weights();
    w.factors = { profit: 0, confidence: 0, feasibility: 0, risk: 0, data_quality: 0 };
    expect(validateWeights(w)).toContain("Factor weights: at least one weight must be greater than zero.");
  });

  it("rejects non-numeric weights", () => {
    const w = weights();
    w.agent_confidence.NETWORK = Number.NaN;
    expect(validateWeights(w)).toContain("Agent confidence weights: every weight must be a number.");
  });

  it("rejects review >= recommend (equal and inverted)", () => {
    const equal = weights({ thresholds: { recommend: 50, review: 50 } });
    const inverted = weights({ thresholds: { recommend: 40, review: 60 } });
    expect(validateWeights(equal)).toContain("The review threshold must be lower than the recommend threshold.");
    expect(validateWeights(inverted)).toContain("The review threshold must be lower than the recommend threshold.");
  });

  it("rejects thresholds outside 0..100", () => {
    const errors = validateWeights(weights({ thresholds: { recommend: 101, review: -1 } }));
    expect(errors).toContain("The review threshold cannot be below 0.");
    expect(errors).toContain("The recommend threshold cannot exceed 100.");
  });

  it("accepts the boundary values 0 and 100", () => {
    expect(validateWeights(weights({ thresholds: { recommend: 100, review: 0 } }))).toEqual([]);
  });

  it("rejects non-numeric thresholds", () => {
    const errors = validateWeights(weights({ thresholds: { recommend: Number.NaN, review: 10 } }));
    expect(errors).toContain("Thresholds must be numbers.");
  });

  it.each([0, -5, Number.NaN])("rejects profit scale %s", (scale) => {
    expect(validateWeights(weights({ profit_scale_usd: scale }))).toContain(
      "The profit scale must be greater than zero.",
    );
  });
});

describe("payload helpers", () => {
  it("toWeightsPayload drops updated_at and copies nested objects", () => {
    const withTimestamp = { ...DEFAULT_WEIGHTS, updated_at: "2026-10-15T00:00:00Z" };
    const payload = toWeightsPayload(withTimestamp);
    expect(payload).not.toHaveProperty("updated_at");
    expect(payload.factors).not.toBe(DEFAULT_WEIGHTS.factors);
    expect(payload).toEqual(DEFAULT_WEIGHTS);
  });
  it("weightsEqual ignores updated_at and detects edits", () => {
    expect(weightsEqual({ ...DEFAULT_WEIGHTS, updated_at: "x" } as DecisionWeights, DEFAULT_WEIGHTS)).toBe(true);
    const edited = weights();
    edited.factors.profit = 0.31;
    expect(weightsEqual(edited, DEFAULT_WEIGHTS)).toBe(false);
  });
});

describe("agent keys", () => {
  it("covers all eight agents with a default weight each", () => {
    expect(AGENT_KEYS).toEqual(["NETWORK", "FLEET", "MAINTENANCE", "CREW", "CARGO", "WEATHER", "FINANCE", "EMISSIONS"]);
    expect(Object.keys(DEFAULT_WEIGHTS.agent_confidence)).toEqual(AGENT_KEYS);
    expect(DEFAULT_WEIGHTS.agent_confidence.WEATHER).toBe(0.1);
    expect(DEFAULT_WEIGHTS.agent_confidence.EMISSIONS).toBe(0.05);
  });
});
