import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RecommendationView } from "./RecommendationView";

describe("RecommendationView", () => {
  it("says so when there is no recommendation", () => {
    render(<RecommendationView recommendation={null} />);
    expect(screen.getByText("[NO RECOMMENDATION YET]")).toBeInTheDocument();
  });

  it("labels fields and formats money, confidence, and booleans", () => {
    render(
      <RecommendationView
        recommendation={{
          route: "DEL-BOM",
          action: "INCREASE_FREQUENCY",
          expected_profit_impact: 19557,
          weekly_profit_usd: -4617,
          confidence: 0.95,
          reviewed: true,
        }}
      />,
    );

    expect(screen.getByText("Route")).toBeInTheDocument();
    expect(screen.getByText("DEL-BOM")).toBeInTheDocument();
    expect(screen.getByText("Expected Profit Impact")).toBeInTheDocument();
    expect(screen.getByText("$19,557")).toBeInTheDocument();
    expect(screen.getByText("-$4,617")).toBeInTheDocument();
    expect(screen.getByText("95%")).toBeInTheDocument();
    expect(screen.getByText("true")).toBeInTheDocument();
  });

  it("renders list fields, including an empty one", () => {
    render(<RecommendationView recommendation={{ risks: ["crew scheduling", "fuel price"], blockers: [] }} />);

    expect(screen.getByText("Risks (2)")).toBeInTheDocument();
    expect(screen.getByText("crew scheduling")).toBeInTheDocument();
    expect(screen.getByText("Blockers (0)")).toBeInTheDocument();
    expect(screen.getByText("[NONE]")).toBeInTheDocument();
  });

  it("serializes non-string list items", () => {
    render(<RecommendationView recommendation={{ risks: [{ kind: "weather" }] }} />);
    expect(screen.getByText('{"kind":"weather"}')).toBeInTheDocument();
  });

  it("renders the reasoning as prose, and omits it when it isn't text", () => {
    const { unmount } = render(<RecommendationView recommendation={{ reasoning: "Demand exceeds capacity." }} />);
    expect(screen.getByText("Reasoning")).toBeInTheDocument();
    expect(screen.getByText("Demand exceeds capacity.")).toBeInTheDocument();
    unmount();

    render(<RecommendationView recommendation={{ route: "DEL-BOM", reasoning: 42 }} />);
    expect(screen.queryByText("Reasoning")).not.toBeInTheDocument();
  });

  it("formats finance and emissions fields readably", () => {
    render(
      <RecommendationView
        recommendation={{
          break_even_fuel_price_usd_per_gallon: 6.1,
          fuel_headroom_pct: 34.2,
          profit_change_if_fuel_up_10pct_usd: -1200,
          co2_change_tonnes_per_week: 12.44,
          co2_per_passenger_kg_before: 58.2,
          co2_per_passenger_kg_after: 61,
          other_number: 7,
        }}
      />,
    );
    expect(screen.getByText("$6.10/gal")).toBeInTheDocument();
    expect(screen.getByText("34%")).toBeInTheDocument();
    expect(screen.getByText("-$1,200")).toBeInTheDocument();
    expect(screen.getByText("+12.4 t/wk")).toBeInTheDocument();
    expect(screen.getByText("58 kg")).toBeInTheDocument();
    expect(screen.getByText("61 kg")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });
});
