import { useQuery } from "@tanstack/react-query";
import type { EventRecord } from "../types";
import { apiFetch } from "./client";

export interface EventFilters {
  run_id?: string;
  agent_execution_id?: string;
  event_type?: string;
  severity?: string;
  entity_type?: string;
  since?: string;
  limit?: number;
}

export function useEvents(filters: EventFilters) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const query = params.toString();

  return useQuery({
    queryKey: ["events", filters],
    queryFn: () => apiFetch<EventRecord[]>(`/api/events${query ? `?${query}` : ""}`),
  });
}
