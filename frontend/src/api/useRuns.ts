import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { OrchestrationRun, RunDetail, RunGraph } from "../types";
import { apiFetch } from "./client";

export function useRuns() {
  return useQuery({
    queryKey: ["runs"],
    queryFn: () => apiFetch<OrchestrationRun[]>("/api/runs"),
  });
}

export function useRunDetail(runId: string | undefined) {
  return useQuery({
    queryKey: ["runs", runId],
    queryFn: () => apiFetch<RunDetail>(`/api/runs/${runId}`),
    enabled: Boolean(runId),
  });
}

export function useRunGraph(runId: string | undefined) {
  return useQuery({
    queryKey: ["runs", runId, "graph"],
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
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}
