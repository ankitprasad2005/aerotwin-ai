import type { Verdict } from "../types/api";
import { FACTOR_KEYS, FACTOR_LABELS } from "./weights";

export interface BreakdownRow {
  key: string;
  label: string;
  weight: number;
  value: number;
  contribution: number;
}

export interface ReadValidation {
  score: number | null;
  verdict: Verdict | null;
  risk: string | null;
  constraints: string | null;
  conflicts: string[];
  warnings: string[];
  breakdown: BreakdownRow[];
}

const VERDICTS: readonly string[] = ["RECOMMEND", "REVIEW", "REJECT"];

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

/** Reads `Decision.validation_result` defensively. Decisions created before the weighted engine
 * have no score, verdict, warnings or breakdown; anything missing or of the wrong type comes back
 * as null / [] so views render a dash instead of crashing. */
export function readValidation(raw: unknown): ReadValidation {
  const source = typeof raw === "object" && raw !== null && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const verdict = typeof source.verdict === "string" && VERDICTS.includes(source.verdict) ? (source.verdict as Verdict) : null;

  const breakdown: BreakdownRow[] = [];
  const rawBreakdown = source.score_breakdown;
  if (typeof rawBreakdown === "object" && rawBreakdown !== null && !Array.isArray(rawBreakdown)) {
    const entries = rawBreakdown as Record<string, unknown>;
    const known: string[] = FACTOR_KEYS.filter((key) => key in entries);
    const extra = Object.keys(entries).filter((key) => !FACTOR_KEYS.includes(key as never));
    for (const key of [...known, ...extra]) {
      const entry = entries[key];
      if (typeof entry !== "object" || entry === null) continue;
      const row = entry as Record<string, unknown>;
      const weight = num(row.weight);
      const value = num(row.value);
      const contribution = num(row.contribution);
      if (weight === null || value === null || contribution === null) continue;
      breakdown.push({
        key,
        label: FACTOR_LABELS[key as keyof typeof FACTOR_LABELS] ?? key,
        weight,
        value,
        contribution,
      });
    }
  }

  return {
    score: num(source.score),
    verdict,
    risk: typeof source.risk === "string" ? source.risk : null,
    constraints: typeof source.constraints === "string" ? source.constraints : null,
    conflicts: strings(source.conflicts),
    warnings: strings(source.warnings),
    breakdown,
  };
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  RECOMMEND: "Recommend",
  REVIEW: "Review",
  REJECT: "Reject",
};

export const VERDICT_HELP: Record<Verdict, string> = {
  RECOMMEND: "Score is at or above the recommend threshold and nothing blocks it.",
  REVIEW: "Score is between the review and recommend thresholds: a human should look at it.",
  REJECT: "A blocking conflict exists, or the score is below the review threshold.",
};
