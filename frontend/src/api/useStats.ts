import { useQuery } from "@tanstack/react-query";
import type { Stats, StatsRun } from "../types/api";
import { apiFetch } from "./client";

export const statsKeys = {
  summary: ["stats"] as const,
  runs: (limit: number) => ["stats", "runs", limit] as const,
};

// Stats are aggregates over the whole database, so they also refresh on a timer: the WebSocket
// only tells the page about events, not about e.g. tokens aging out of the 24 h window.
const STATS_REFRESH_MS = 30_000;

export function useStats() {
  return useQuery({
    queryKey: statsKeys.summary,
    queryFn: () => apiFetch<Stats>("/api/stats"),
    refetchInterval: STATS_REFRESH_MS,
  });
}

export function useStatsRuns(limit = 100) {
  return useQuery({
    queryKey: statsKeys.runs(limit),
    queryFn: () => apiFetch<StatsRun[]>(`/api/stats/runs?limit=${limit}`),
  });
}
