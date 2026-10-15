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

/** One-line summary of an agent's structured output for the agents table. The five agents emit
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
