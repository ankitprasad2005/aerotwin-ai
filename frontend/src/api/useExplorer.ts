import { useQuery } from "@tanstack/react-query";
import type { CatalogEntry, ExplorerPage } from "../types/explorer";
import { rowsQueryString, type ExplorerQuery } from "../utils/explorer";
import { apiBaseUrl } from "./baseUrls";
import { apiFetch } from "./client";

export const explorerKeys = {
  catalog: ["data", "catalog"] as const,
  rows: (key: string, query: string) => ["data", "rows", key, query] as const,
};

export function useCatalog() {
  return useQuery({ queryKey: explorerKeys.catalog, queryFn: () => apiFetch<CatalogEntry[]>("/api/data/catalog") });
}

export function useExplorerRows(key: string | null, query: ExplorerQuery) {
  const qs = rowsQueryString(query);
  return useQuery({
    queryKey: explorerKeys.rows(key ?? "", qs),
    queryFn: () => apiFetch<ExplorerPage>(`/api/data/${encodeURIComponent(key ?? "")}/rows?${qs}`),
    enabled: key !== null,
    // Keep the old page while paging/sorting the same dataset, never another dataset's columns.
    placeholderData: (previous, previousQuery) => (previousQuery?.queryKey[2] === key ? previous : undefined),
  });
}

/** Link that downloads the filtered rows (all pages) as CSV. */
export function exportUrl(key: string, query: ExplorerQuery): string {
  const qs = rowsQueryString(query, false);
  return `${apiBaseUrl()}/api/data/${encodeURIComponent(key)}/export.csv${qs ? `?${qs}` : ""}`;
}
