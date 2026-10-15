import { describe, expect, it } from "vitest";
import { agentLabel, summarizeRecommendation } from "./recommendation";

describe("summarizeRecommendation", () => {
  it("returns a dash and no confidence for a null recommendation", () => {
    expect(summarizeRecommendation(null)).toEqual({ confidence: null, headline: "—", citedSources: [] });
  });

  it("summarises a network recommendation with its profit", () => {
    const s = summarizeRecommendation({
      route: "BOM-DEL",
      action: "INCREASE_FREQUENCY",
      expected_profit_impact: 85000,
      confidence: 0.82,
      cited_sources: ["fuel:eia:2026-10-10"],
    });
    expect(s.headline).toBe("BOM-DEL: increase frequency (+$85,000/wk)");
    expect(s.confidence).toBe(0.82);
    expect(s.citedSources).toEqual(["fuel:eia:2026-10-10"]);
  });

  it("omits the profit when it is missing", () => {
    expect(summarizeRecommendation({ route: "BOM-DEL", action: "MAINTAIN" }).headline).toBe("BOM-DEL: maintain");
  });

  it("summarises fleet and crew assignments", () => {
    expect(
      summarizeRecommendation({ route: "BOM-DEL", assignment_action: "REASSIGN", aircraft_tail_number: "VT-ABC" })
        .headline,
    ).toBe("BOM-DEL · reassign · VT-ABC");
    expect(
      summarizeRecommendation({ assignment_action: "NO_CHANGE", crew_availability: "INSUFFICIENT" }).headline,
    ).toBe("no change · crew insufficient");
  });

  it("summarises cargo with and without a route", () => {
    expect(summarizeRecommendation({ route: "BOM-DEL", cargo_stance: "OPPOSES" }).headline).toBe(
      "BOM-DEL: cargo opposes",
    );
    expect(summarizeRecommendation({ cargo_stance: "NEUTRAL" }).headline).toBe("cargo neutral");
  });

  it("summarises maintenance by counting aircraft", () => {
    expect(
      summarizeRecommendation({ grounded_aircraft: ["A", "B"], at_risk_aircraft: ["C"] }).headline,
    ).toBe("2 grounded, 1 at risk");
    expect(summarizeRecommendation({ grounded_aircraft: [] }).headline).toBe("0 grounded, 0 at risk");
  });

  it("falls back to a dash for an unknown schema and ignores bad fields", () => {
    const s = summarizeRecommendation({ confidence: "high", cited_sources: "x", something: 1 });
    expect(s).toEqual({ confidence: null, headline: "—", citedSources: [] });
  });

  it("filters non-string cited sources and non-finite confidence", () => {
    const s = summarizeRecommendation({ confidence: Number.NaN, cited_sources: ["a", 1, null] });
    expect(s.confidence).toBeNull();
    expect(s.citedSources).toEqual(["a"]);
  });

  it("truncates very long headlines", () => {
    const s = summarizeRecommendation({ route: "R".repeat(300), action: "MAINTAIN" });
    expect(s.headline.length).toBeLessThanOrEqual(90);
  });

  it("treats blank strings as absent", () => {
    expect(summarizeRecommendation({ route: "  ", action: "  " }).headline).toBe("—");
  });
});

describe("agentLabel", () => {
  it("capitalises and strips the _AGENT suffix", () => {
    expect(agentLabel("NETWORK")).toBe("Network");
    expect(agentLabel("CARGO_AGENT")).toBe("Cargo");
  });
});
