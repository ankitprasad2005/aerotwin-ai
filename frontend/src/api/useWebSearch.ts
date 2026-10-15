import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { WebSearchCacheEntry, WebSearchResponse, WebSearchStatus } from "../types/api";
import { apiFetch } from "./client";

export const MAX_SEARCH_QUERY_LENGTH = 200;

export const webSearchKeys = {
  status: ["web-search", "status"] as const,
  cache: (limit: number) => ["web-search", "cache", limit] as const,
};

export function useWebSearchStatus() {
  return useQuery({
    queryKey: webSearchKeys.status,
    queryFn: () => apiFetch<WebSearchStatus>("/api/web-search/status"),
  });
}

export function useWebSearchCache(limit = 50) {
  return useQuery({
    queryKey: webSearchKeys.cache(limit),
    queryFn: () => apiFetch<WebSearchCacheEntry[]>(`/api/web-search/cache?limit=${limit}`),
  });
}

/** Runs a manual search. A fresh result lands in the server-side cache, so the cache list is
 * invalidated afterwards. */
export function useWebSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (query: string) =>
      apiFetch<WebSearchResponse>("/api/web-search", {
        method: "POST",
        body: JSON.stringify({ query: query.trim() }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["web-search", "cache"] });
    },
  });
}
