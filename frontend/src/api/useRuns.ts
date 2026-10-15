import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { KnowledgeGraph, OrchestrationRun, RunDetail, RunGraph } from "../types";
import type { AgentMessage, RunEvidenceEntry } from "../types/api";
import { apiFetch } from "./client";

// Centralized so every hook here (and every hook added in later tasks that
// touches runs) agrees on the exact key shape — a typo in an inline array
// literal would silently create a disconnected, never-invalidated cache entry.
export const runKeys = {
  all: ["runs"] as const,
  detail: (runId: string | undefined) => ["runs", runId] as const,
  graph: (runId: string | undefined) => ["runs", runId, "graph"] as const,
  knowledge: (runId: string | undefined) => ["runs", runId, "knowledge-graph"] as const,
  evidence: (runId: string | undefined) => ["runs", runId, "evidence"] as const,
  messages: (runId: string | undefined) => ["runs", runId, "messages"] as const,
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

export function useRunKnowledgeGraph(runId: string | undefined) {
  return useQuery({
    queryKey: runKeys.knowledge(runId),
    queryFn: () => apiFetch<KnowledgeGraph>(`/api/runs/${runId}/knowledge-graph`),
    enabled: Boolean(runId),
  });
}

export function useRunEvidence(runId: string | undefined) {
  return useQuery({
    queryKey: runKeys.evidence(runId),
    queryFn: () => apiFetch<RunEvidenceEntry[]>(`/api/runs/${runId}/evidence`),
    enabled: Boolean(runId),
  });
}

export function useRunMessages(runId: string | undefined) {
  return useQuery({
    queryKey: runKeys.messages(runId),
    queryFn: () => apiFetch<AgentMessage[]>(`/api/runs/${runId}/messages`),
    enabled: Boolean(runId),
  });
}

/** Runs the pipeline again inside an existing run, prompted by a new objective. */
export function useAddRunPrompt(runId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (objective: string) =>
      apiFetch<OrchestrationRun>(`/api/runs/${runId}/prompts`, {
        method: "POST",
        body: JSON.stringify({ objective }),
      }),
    onSuccess: () => {
      // Prefix match: the run's detail, graph and knowledge graph all gained an iteration.
      void queryClient.invalidateQueries({ queryKey: runKeys.all });
    },
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
