import type { DecisionWeights, WeightAgent, WeightFactor } from "../types/api";

export const FACTOR_KEYS: WeightFactor[] = ["profit", "confidence", "feasibility", "risk", "data_quality"];
export const AGENT_KEYS: WeightAgent[] = [
  "NETWORK",
  "FLEET",
  "MAINTENANCE",
  "CREW",
  "CARGO",
  "WEATHER",
  "FINANCE",
  "EMISSIONS",
];

export const FACTOR_LABELS: Record<WeightFactor, string> = {
  profit: "Profit",
  confidence: "Confidence",
  feasibility: "Feasibility",
  risk: "Risk",
  data_quality: "Data quality",
};

export const FACTOR_HELP: Record<WeightFactor, string> = {
  profit: "Weekly profit impact, squashed onto 0-1 by the profit scale.",
  confidence: "Agent-weighted mean of the agents' stated confidence.",
  feasibility: "Share of constraint checks that passed.",
  risk: "Falls with each blocking conflict and warning.",
  data_quality: "Mean reliability of the evidence the agents cited.",
};

export const DEFAULT_WEIGHTS: DecisionWeights = {
  factors: { profit: 0.424, confidence: 0.227, feasibility: 0, risk: 0.227, data_quality: 0.122 },
  agent_confidence: { NETWORK: 0.35, FLEET: 0.2, MAINTENANCE: 0.15, CREW: 0.15, CARGO: 0.15,
    WEATHER: 0.1,
    FINANCE: 0.1,
    EMISSIONS: 0.05,
  },
  thresholds: { recommend: 76, review: 66 },
  profit_scale_usd: 10000,
};

/** Weights as shares of their group total (each group sums to 1). A group whose weights are all
 * zero has no meaningful share, so every share is 0 rather than NaN. */
export function normalizeGroup<K extends string>(group: Record<K, number>): Record<K, number> {
  const keys = Object.keys(group) as K[];
  const total = keys.reduce((sum, key) => sum + (Number.isFinite(group[key]) ? Math.max(0, group[key]) : 0), 0);
  const result = {} as Record<K, number>;
  for (const key of keys) {
    const value = Number.isFinite(group[key]) ? Math.max(0, group[key]) : 0;
    result[key] = total > 0 ? value / total : 0;
  }
  return result;
}

function groupErrors(name: string, group: Record<string, number>): string[] {
  const errors: string[] = [];
  const values = Object.values(group);
  if (values.some((value) => !Number.isFinite(value))) {
    errors.push(`${name}: every weight must be a number.`);
    return errors;
  }
  if (values.some((value) => value < 0)) errors.push(`${name}: weights cannot be negative.`);
  else if (values.reduce((sum, value) => sum + value, 0) <= 0) {
    errors.push(`${name}: at least one weight must be greater than zero.`);
  }
  return errors;
}

/** Mirrors the backend rules: non-negative weights, positive group sums, 0 <= review < recommend
 * <= 100 and a positive profit scale. Returns human-readable errors (empty when valid). */
export function validateWeights(weights: DecisionWeights): string[] {
  const errors = [
    ...groupErrors("Factor weights", weights.factors),
    ...groupErrors("Agent confidence weights", weights.agent_confidence),
  ];
  const { recommend, review } = weights.thresholds;
  if (!Number.isFinite(recommend) || !Number.isFinite(review)) {
    errors.push("Thresholds must be numbers.");
  } else {
    if (review < 0) errors.push("The review threshold cannot be below 0.");
    if (recommend > 100) errors.push("The recommend threshold cannot exceed 100.");
    if (review >= recommend) errors.push("The review threshold must be lower than the recommend threshold.");
  }
  if (!Number.isFinite(weights.profit_scale_usd) || weights.profit_scale_usd <= 0) {
    errors.push("The profit scale must be greater than zero.");
  }
  return errors;
}

/** Strips server-only fields (updated_at) so the PUT body is exactly the editable shape. */
export function toWeightsPayload(weights: DecisionWeights): DecisionWeights {
  return {
    factors: { ...weights.factors },
    agent_confidence: { ...weights.agent_confidence },
    thresholds: { ...weights.thresholds },
    profit_scale_usd: weights.profit_scale_usd,
  };
}

export function weightsEqual(a: DecisionWeights, b: DecisionWeights): boolean {
  return JSON.stringify(toWeightsPayload(a)) === JSON.stringify(toWeightsPayload(b));
}
