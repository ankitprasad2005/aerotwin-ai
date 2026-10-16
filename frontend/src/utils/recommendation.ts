import { formatSignedUsd, truncate } from "./format";

export interface RecommendationSummary {
  confidence: number | null;
  headline: string;
  citedSources: string[];
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function words(value: string): string {
  return value.replace(/_/g, " ").toLowerCase();
}

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

/** One-line summary of an agent's structured output for the agents table. The eight agents emit
 * different schemas, so this keys off which fields are present rather than the agent type. */
export function summarizeRecommendation(recommendation: Record<string, unknown> | null): RecommendationSummary {
  if (!recommendation) return { confidence: null, headline: "—", citedSources: [] };

  const confidence =
    typeof recommendation.confidence === "number" && Number.isFinite(recommendation.confidence)
      ? recommendation.confidence
      : null;
  const citedSources = list(recommendation.cited_sources);
  const route = str(recommendation.route);

  let headline: string | null = null;
  const action = str(recommendation.action);
  const assignment = str(recommendation.assignment_action);
  const stance = str(recommendation.cargo_stance);

  if (action && route) {
    // Network. Maintenance also has `actions`, but only the network schema has a single `action`.
    const profit = recommendation.expected_profit_impact;
    headline = `${route}: ${words(action)}${typeof profit === "number" ? ` (${formatSignedUsd(profit)}/wk)` : ""}`;
  } else if (str(recommendation.weather_risk)) {
    const days = recommendation.disruption_days_next_7;
    headline = [
      route,
      `weather risk ${str(recommendation.weather_risk)}`,
      typeof days === "number" ? `${days} disruption ${days === 1 ? "day" : "days"}` : null,
    ]
      .filter(Boolean)
      .join(" · ");
  } else if (str(recommendation.financial_risk)) {
    const breakEven = recommendation.break_even_fuel_price_usd_per_gallon;
    const headroom = recommendation.fuel_headroom_pct;
    const fuel =
      typeof breakEven === "number"
        ? `break-even fuel $${breakEven.toFixed(2)}/gal${typeof headroom === "number" ? ` (${headroom >= 0 ? "+" : ""}${Math.round(headroom)}%)` : ""}`
        : "no fuel break-even";
    headline = [route, fuel, `risk ${str(recommendation.financial_risk)}`].filter(Boolean).join(" · ");
  } else if (str(recommendation.emissions_stance)) {
    const change = recommendation.co2_change_tonnes_per_week;
    const before = recommendation.co2_per_passenger_kg_before;
    const after = recommendation.co2_per_passenger_kg_after;
    headline = [
      route,
      typeof change === "number" ? `${change >= 0 ? "+" : ""}${change.toFixed(1)} t CO2/wk` : null,
      typeof before === "number" && typeof after === "number"
        ? `${Math.round(before)}→${Math.round(after)} kg/pax`
        : null,
      words(String(str(recommendation.emissions_stance))),
    ]
      .filter(Boolean)
      .join(" · ");
  } else if (stance) {
    headline = `${route ? `${route}: ` : ""}cargo ${words(stance)}`;
  } else if (assignment) {
    const tail = str(recommendation.aircraft_tail_number);
    const availability = str(recommendation.crew_availability);
    headline = [route, words(assignment), tail, availability ? `crew ${words(availability)}` : null]
      .filter(Boolean)
      .join(" · ");
  } else if (Array.isArray(recommendation.grounded_aircraft)) {
    const grounded = list(recommendation.grounded_aircraft).length;
    const atRisk = list(recommendation.at_risk_aircraft).length;
    headline = `${grounded} grounded, ${atRisk} at risk`;
  }

  return {
    confidence,
    headline: headline ? truncate(headline, 90) : "—",
    citedSources,
  };
}

/** NETWORK -> "Network", DECISION_ENGINE -> "Decision engine". */
export function agentLabel(agentType: string): string {
  const base = agentType.replace(/_AGENT$/, "").replace(/_/g, " ").toLowerCase();
  return base.charAt(0).toUpperCase() + base.slice(1);
}
