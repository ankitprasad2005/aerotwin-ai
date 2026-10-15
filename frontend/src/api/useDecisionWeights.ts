import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { DecisionWeights, DecisionWeightsResponse } from "../types/api";
import { toWeightsPayload } from "../utils/weights";
import { apiFetch } from "./client";

export const weightsKey = ["decision-weights"] as const;

export function useDecisionWeights() {
  return useQuery({
    queryKey: weightsKey,
    queryFn: () => apiFetch<DecisionWeightsResponse>("/api/decision-weights"),
  });
}

export function useSaveDecisionWeights() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (weights: DecisionWeights) =>
      apiFetch<DecisionWeightsResponse>("/api/decision-weights", {
        method: "PUT",
        body: JSON.stringify(toWeightsPayload(weights)),
      }),
    onSuccess: (saved) => {
      queryClient.setQueryData(weightsKey, saved);
    },
  });
}
