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
    expect(agentLabel("DECISION_ENGINE")).toBe("Decision engine");
  });
});

describe("summarizeRecommendation (weather, finance, emissions)", () => {
  it("summarises weather", () => {
    expect(summarizeRecommendation({ route: "DEL-BOM", weather_risk: "HIGH", disruption_days_next_7: 3, confidence: 0.6 }).headline).toBe(
      "DEL-BOM · weather risk HIGH · 3 disruption days",
    );
    expect(summarizeRecommendation({ weather_risk: "LOW", disruption_days_next_7: 1 }).headline).toBe("weather risk LOW · 1 disruption day");
    expect(summarizeRecommendation({ weather_risk: "LOW" }).headline).toBe("weather risk LOW");
  });

  it("summarises finance, including a missing break-even and negative headroom", () => {
    expect(
      summarizeRecommendation({ route: "DEL-BOM", break_even_fuel_price_usd_per_gallon: 6.1, fuel_headroom_pct: 34.2, financial_risk: "LOW" }).headline,
    ).toBe("DEL-BOM · break-even fuel $6.10/gal (+34%) · risk LOW");
    expect(
      summarizeRecommendation({ break_even_fuel_price_usd_per_gallon: 2, fuel_headroom_pct: -10, financial_risk: "HIGH" }).headline,
    ).toBe("break-even fuel $2.00/gal (-10%) · risk HIGH");
    expect(summarizeRecommendation({ break_even_fuel_price_usd_per_gallon: 3, fuel_headroom_pct: null, financial_risk: "LOW" }).headline).toBe(
      "break-even fuel $3.00/gal · risk LOW",
    );
    expect(
      summarizeRecommendation({ route: "DEL-BOM", break_even_fuel_price_usd_per_gallon: null, fuel_headroom_pct: null, financial_risk: "MODERATE" }).headline,
    ).toBe("DEL-BOM · no fuel break-even · risk MODERATE");
  });

  it("summarises emissions", () => {
    expect(
      summarizeRecommendation({
        route: "DEL-BOM",
        co2_change_tonnes_per_week: 12.44,
        co2_per_passenger_kg_before: 58,
        co2_per_passenger_kg_after: 61,
        emissions_stance: "OPPOSES",
      }).headline,
    ).toBe("DEL-BOM · +12.4 t CO2/wk · 58→61 kg/pax · opposes");
    expect(summarizeRecommendation({ co2_change_tonnes_per_week: -2, emissions_stance: "SUPPORTS" }).headline).toBe("-2.0 t CO2/wk · supports");
    expect(summarizeRecommendation({ emissions_stance: "NEUTRAL" }).headline).toBe("neutral");
  });

  it("labels the new agents", () => {
    expect(agentLabel("WEATHER_AGENT")).toBe("Weather");
    expect(agentLabel("EMISSIONS")).toBe("Emissions");
  });
});
