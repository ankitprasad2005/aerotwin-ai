import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  AirportWeather,
  DatasetInfo,
  DatasetRefreshResult,
  DgcaTrafficRow,
  FuelPricePoint,
  FxRatePoint,
  MarketRoute,
} from "../types/api";
import { apiFetch } from "./client";
import { statsKeys } from "./useStats";

export const datasetKeys = {
  all: ["datasets"] as const,
  fuel: (days: number) => ["datasets", "fuel-prices", days] as const,
  fx: (quote: string, days: number) => ["datasets", "fx-rates", quote, days] as const,
  routes: (origin: string, destination: string) => ["datasets", "market-routes", origin, destination] as const,
  dgca: ["datasets", "dgca-traffic"] as const,
  weather: ["datasets", "weather"] as const,
};

export function useDatasets() {
  return useQuery({ queryKey: datasetKeys.all, queryFn: () => apiFetch<DatasetInfo[]>("/api/datasets") });
}

/** Refreshes the given sources (all of them when omitted). The data underneath every dataset view
 * changes, so the whole `datasets` prefix and the header stats are invalidated. */
export function useRefreshDatasets() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sources?: string[]) =>
      apiFetch<DatasetRefreshResult[]>("/api/datasets/refresh", {
        method: "POST",
        body: JSON.stringify(sources && sources.length > 0 ? { sources } : {}),
      }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: datasetKeys.all });
      void queryClient.invalidateQueries({ queryKey: statsKeys.summary });
    },
  });
}

export function useFuelPrices(days = 90) {
  return useQuery({
    queryKey: datasetKeys.fuel(days),
    queryFn: () => apiFetch<FuelPricePoint[]>(`/api/datasets/fuel-prices?days=${days}`),
  });
}

export function useFxRates(days = 90, quote = "INR") {
  return useQuery({
    queryKey: datasetKeys.fx(quote, days),
    queryFn: () => apiFetch<FxRatePoint[]>(`/api/datasets/fx-rates?quote=${encodeURIComponent(quote)}&days=${days}`),
  });
}

export function useMarketRoutes(origin = "", destination = "") {
  const params = new URLSearchParams();
  if (origin) params.set("origin", origin);
  if (destination) params.set("destination", destination);
  const query = params.toString();
  return useQuery({
    queryKey: datasetKeys.routes(origin, destination),
    queryFn: () => apiFetch<MarketRoute[]>(`/api/datasets/market-routes${query ? `?${query}` : ""}`),
  });
}

export function useDgcaTraffic() {
  return useQuery({
    queryKey: datasetKeys.dgca,
    queryFn: () => apiFetch<DgcaTrafficRow[]>("/api/datasets/dgca-traffic"),
  });
}

export function useWeather() {
  return useQuery({
    queryKey: datasetKeys.weather,
    queryFn: () => apiFetch<AirportWeather[]>("/api/datasets/weather"),
  });
}
