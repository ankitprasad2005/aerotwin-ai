import type { StatsRun } from "../types/api";

export interface RunFilters {
  status: string; // "" = all
  verdict: string; // "" = all, "NONE" = no verdict
  query: string;
}

export const EMPTY_FILTERS: RunFilters = { status: "", verdict: "", query: "" };

export function filterRuns(runs: readonly StatsRun[], filters: RunFilters): StatsRun[] {
  const query = filters.query.trim().toLowerCase();
  return runs.filter((run) => {
    if (filters.status && run.status !== filters.status) return false;
    if (filters.verdict) {
      const verdict = run.decision?.verdict ?? null;
      if (filters.verdict === "NONE" ? verdict !== null : verdict !== filters.verdict) return false;
    }
    if (query && !run.objective.toLowerCase().includes(query) && !(run.decision?.summary ?? "").toLowerCase().includes(query)) {
      return false;
    }
    return true;
  });
}

export function hasActiveFilters(filters: RunFilters): boolean {
  return filters.status !== "" || filters.verdict !== "" || filters.query.trim() !== "";
}
