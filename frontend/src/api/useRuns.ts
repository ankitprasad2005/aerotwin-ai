import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { OrchestrationRun, RunDetail, RunGraph } from "../types";
import { apiFetch } from "./client";

// Centralized so every hook here (and every hook added in later tasks that
// touches runs) agrees on the exact key shape — a typo in an inline array
// literal would silently create a disconnected, never-invalidated cache entry.
export const runKeys = {
  all: ["runs"] as const,
  detail: (runId: string | undefined) => ["runs", runId] as const,
  graph: (runId: string | undefined) => ["runs", runId, "graph"] as const,
};

export function useRuns() {
  return useQuery({
    queryKey: runKeys.all,
    queryFn: () => apiFetch<OrchestrationRun[]>("/api/runs"),
  });
}

export function useRunDetail(runId: string | undefined) {
  return useQuery({
    queryKey: runKeys.detail(runId),
    queryFn: () => apiFetch<RunDetail>(`/api/runs/${runId}`),
    enabled: Boolean(runId),
  });
}

export function useRunGraph(runId: string | undefined) {
  return useQuery({
    queryKey: runKeys.graph(runId),
    queryFn: () => apiFetch<RunGraph>(`/api/runs/${runId}/graph`),
    enabled: Boolean(runId),
  });
}

export function useCreateRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (objective: string) =>
      apiFetch<OrchestrationRun>("/api/runs", {
        method: "POST",
        body: JSON.stringify({ objective }),
      }),
    onSuccess: () => {
      // Broad prefix match is intentional: also refetches any currently-mounted
      // useRunDetail/useRunGraph, which is a cheap no-op if nothing changed.
      void queryClient.invalidateQueries({ queryKey: runKeys.all });
    },
  });
}
