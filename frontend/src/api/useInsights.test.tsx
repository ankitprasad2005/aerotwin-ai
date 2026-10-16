import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { api, defaultHandlers, makeStats, makeWeights } from "../test/fixtures";
import { server } from "../test/mswServer";
import { createQueryWrapper } from "../test/renderWithQueryClient";
import { ApiError } from "./client";
import { useDecisionWeights, useSaveDecisionWeights } from "./useDecisionWeights";
import {
  useDatasets,
  useDgcaTraffic,
  useWeather,
  useFuelPrices,
  useFxRates,
  useMarketRoutes,
  useRefreshDatasets,
} from "./useDatasets";
import { useRunEvidence } from "./useRuns";
import { useStats, useStatsRuns } from "./useStats";
import { useWebSearch, useWebSearchCache, useWebSearchStatus } from "./useWebSearch";

describe("stats hooks", () => {
  it("useStats loads /api/stats", async () => {
    server.use(...defaultHandlers());
    const { result } = renderHook(() => useStats(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(makeStats());
  });

  it("useStats surfaces API errors", async () => {
    server.use(http.get(api("/api/stats"), () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    const { result } = renderHook(() => useStats(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(ApiError);
  });

  it("useStatsRuns passes the limit", async () => {
    let limit: string | null = null;
    server.use(
      http.get(api("/api/stats/runs"), ({ request }) => {
        limit = new URL(request.url).searchParams.get("limit");
        return HttpResponse.json([]);
      }),
    );
    const { result } = renderHook(() => useStatsRuns(25), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(limit).toBe("25");
  });

  it("useStatsRuns defaults to 100", async () => {
    let limit: string | null = null;
    server.use(
      http.get(api("/api/stats/runs"), ({ request }) => {
        limit = new URL(request.url).searchParams.get("limit");
        return HttpResponse.json([]);
      }),
    );
    const { result } = renderHook(() => useStatsRuns(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(limit).toBe("100");
  });
});

describe("dataset hooks", () => {
  it("load the dataset list and each series", async () => {
    server.use(...defaultHandlers());
    const wrapper = createQueryWrapper();
    const datasets = renderHook(() => useDatasets(), { wrapper });
    const fuel = renderHook(() => useFuelPrices(), { wrapper });
    const fx = renderHook(() => useFxRates(), { wrapper });
    const dgca = renderHook(() => useDgcaTraffic(), { wrapper });
    await waitFor(() => expect(datasets.result.current.data).toHaveLength(6));
    await waitFor(() => expect(fuel.result.current.data).toHaveLength(3));
    await waitFor(() => expect(fx.result.current.data).toHaveLength(2));
    await waitFor(() => expect(dgca.result.current.data).toHaveLength(2));
    const weather = renderHook(() => useWeather(), { wrapper });
    await waitFor(() => expect(weather.result.current.data).toHaveLength(2));
  });

  it("sends days and quote query parameters", async () => {
    const seen: string[] = [];
    server.use(
      http.get(api("/api/datasets/fuel-prices"), ({ request }) => {
        seen.push(new URL(request.url).search);
        return HttpResponse.json([]);
      }),
      http.get(api("/api/datasets/fx-rates"), ({ request }) => {
        seen.push(new URL(request.url).search);
        return HttpResponse.json([]);
      }),
    );
    const wrapper = createQueryWrapper();
    const fuel = renderHook(() => useFuelPrices(30), { wrapper });
    const fx = renderHook(() => useFxRates(45, "EUR"), { wrapper });
    await waitFor(() => expect(fuel.result.current.isSuccess && fx.result.current.isSuccess).toBe(true));
    expect(seen).toContain("?days=30");
    expect(seen).toContain("?quote=EUR&days=45");
  });

  it("useMarketRoutes builds its query string from the filters", async () => {
    const seen: string[] = [];
    server.use(
      http.get(api("/api/datasets/market-routes"), ({ request }) => {
        seen.push(new URL(request.url).search);
        return HttpResponse.json([]);
      }),
    );
    const wrapper = createQueryWrapper();
    const none = renderHook(() => useMarketRoutes(), { wrapper });
    const both = renderHook(() => useMarketRoutes("DEL", "BOM"), { wrapper });
    await waitFor(() => expect(none.result.current.isSuccess && both.result.current.isSuccess).toBe(true));
    expect(seen).toContain("");
    expect(seen).toContain("?origin=DEL&destination=BOM");
  });

  it("useRefreshDatasets posts the sources, or an empty body for all", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(api("/api/datasets/refresh"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json([]);
      }),
    );
    const { result } = renderHook(() => useRefreshDatasets(), { wrapper: createQueryWrapper() });
    await act(() => result.current.mutateAsync(["fx"]));
    await act(() => result.current.mutateAsync(undefined));
    await act(() => result.current.mutateAsync([]));
    expect(bodies).toEqual([{ sources: ["fx"] }, {}, {}]);
  });
});

describe("web search hooks", () => {
  it("load status and cache", async () => {
    server.use(...defaultHandlers());
    const wrapper = createQueryWrapper();
    const status = renderHook(() => useWebSearchStatus(), { wrapper });
    const cache = renderHook(() => useWebSearchCache(10), { wrapper });
    await waitFor(() => expect(status.result.current.data?.reachable).toBe(true));
    await waitFor(() => expect(cache.result.current.data).toHaveLength(1));
  });

  it("useWebSearch trims the query and posts it", async () => {
    let body: unknown = null;
    server.use(
      http.post(api("/api/web-search"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ query: "q", cached: false, stale: false, fetched_at: null, results: [] });
      }),
    );
    const { result } = renderHook(() => useWebSearch(), { wrapper: createQueryWrapper() });
    await act(() => result.current.mutateAsync("  india aviation  "));
    expect(body).toEqual({ query: "india aviation" });
  });

  it("useWebSearch exposes a 422 as an ApiError", async () => {
    server.use(http.post(api("/api/web-search"), () => HttpResponse.json({ detail: "too long" }, { status: 422 })));
    const { result } = renderHook(() => useWebSearch(), { wrapper: createQueryWrapper() });
    await act(async () => {
      await result.current.mutateAsync("x").catch(() => undefined);
    });
    expect(result.current.error).toMatchObject({ status: 422, message: "too long" });
  });
});

describe("decision weight hooks", () => {
  it("loads the weights", async () => {
    server.use(...defaultHandlers());
    const { result } = renderHook(() => useDecisionWeights(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.data).toEqual(makeWeights()));
  });

  it("saves without updated_at and caches the response", async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.put(api("/api/decision-weights"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...body, updated_at: "saved" });
      }),
      ...defaultHandlers(),
    );
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => ({ save: useSaveDecisionWeights(), load: useDecisionWeights() }), {
      wrapper,
    });
    await waitFor(() => expect(result.current.load.isSuccess).toBe(true));
    await act(() => result.current.save.mutateAsync({ ...makeWeights() }));
    expect(body).not.toHaveProperty("updated_at");
    await waitFor(() => expect(result.current.load.data?.updated_at).toBe("saved"));
  });

  it("reports validation errors from the server", async () => {
    server.use(
      http.put(api("/api/decision-weights"), () =>
        HttpResponse.json({ detail: [{ msg: "review must be below recommend" }] }, { status: 422 }),
      ),
    );
    const { result } = renderHook(() => useSaveDecisionWeights(), { wrapper: createQueryWrapper() });
    act(() => {
      result.current.mutate(makeWeights());
    });
    await waitFor(() => expect(result.current.error?.message).toBe("review must be below recommend"));
  });
});

describe("useRunEvidence", () => {
  it("loads evidence for a run and stays idle without an id", async () => {
    server.use(...defaultHandlers());
    const wrapper = createQueryWrapper();
    const loaded = renderHook(() => useRunEvidence("run-1"), { wrapper });
    const idle = renderHook(() => useRunEvidence(undefined), { wrapper });
    await waitFor(() => expect(loaded.result.current.data).toHaveLength(1));
    expect(idle.result.current.fetchStatus).toBe("idle");
  });

  it("surfaces a 404", async () => {
    server.use(http.get(api("/api/runs/:id/evidence"), () => HttpResponse.json({ detail: "not found" }, { status: 404 })));
    const { result } = renderHook(() => useRunEvidence("nope"), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
