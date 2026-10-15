// Backend-shaped sample data and MSW handlers for every endpoint the redesigned UI consumes.
// Unit tests start from `defaultHandlers()` and override individual endpoints with `server.use`.
import { http, HttpResponse, type HttpHandler } from "msw";
import type { AgentExecution, Decision, RunDetail, RunIteration } from "../types";
import type {
  DatasetInfo,
  DecisionWeightsResponse,
  DgcaTrafficRow,
  EvidenceItem,
  MarketRoute,
  RunEvidenceEntry,
  Stats,
  StatsRun,
  WebSearchResponse,
} from "../types/api";
import { DEFAULT_WEIGHTS } from "../utils/weights";

export const API = "http://localhost:8000";
export const api = (path: string) => `${API}${path}`;

export function makeStats(patch: Partial<Stats> = {}): Stats {
  return {
    runs_total: 12,
    runs_completed: 9,
    runs_failed: 2,
    runs_running: 1,
    p95_run_duration_ms: 48_500,
    tokens_total: 250_000,
    tokens_last_24h: 42_000,
    decisions_by_verdict: { RECOMMEND: 5, REVIEW: 3, REJECT: 1 },
    latest_fuel_price: { date: "2026-10-10", usd_per_gallon: 2.31 },
    latest_usd_inr: { date: "2026-10-14", rate: 83.42 },
    runs_per_day: [
      { date: "2026-10-13", count: 2 },
      { date: "2026-10-14", count: 4 },
      { date: "2026-10-15", count: 3 },
    ],
    tokens_per_day: [
      { date: "2026-10-13", tokens: 10_000 },
      { date: "2026-10-14", tokens: 20_000 },
      { date: "2026-10-15", tokens: 12_000 },
    ],
    ...patch,
  };
}

export function makeStatsRun(patch: Partial<StatsRun> = {}): StatsRun {
  return {
    id: "run-1",
    objective: "Improve airline profitability",
    status: "COMPLETED",
    created_at: "2026-10-15T10:00:00Z",
    completed_at: "2026-10-15T10:00:40Z",
    duration_ms: 40_000,
    total_tokens: 12_345,
    iterations: 1,
    decision: {
      summary: "Increase BOM-DEL frequency",
      verdict: "RECOMMEND",
      score: 74.2,
      expected_profit_impact: 85_000,
      risk: "LOW",
    },
    ...patch,
  };
}

export function makeDecision(patch: Partial<Decision> = {}): Decision {
  return {
    id: "d1",
    run_id: "run-1",
    summary: "Increase BOM-DEL frequency",
    expected_profit_impact: 85_000,
    expected_revenue_impact: 300_000,
    expected_cost_impact: 215_000,
    confidence: 0.82,
    risks: ["Fuel price volatility"],
    constraints_checked: ["Aircraft available", "Crew available"],
    validation_result: {
      risk: "LOW",
      constraints: "PASS",
      conflicts: [],
      warnings: ["Cargo opposes the change"],
      score: 74.2,
      verdict: "RECOMMEND",
      score_breakdown: {
        profit: { weight: 0.3, value: 0.7, contribution: 21 },
        confidence: { weight: 0.2, value: 0.8, contribution: 16 },
        feasibility: { weight: 0.25, value: 1, contribution: 25 },
        risk: { weight: 0.15, value: 0.85, contribution: 12.75 },
        data_quality: { weight: 0.1, value: 0.5, contribution: 5 },
      },
    },
    status: "RECOMMENDED",
    agents_involved: ["NETWORK", "FLEET"],
    created_at: "2026-10-15T10:00:40Z",
    ...patch,
  };
}

export function makeAgent(patch: Partial<AgentExecution> = {}): AgentExecution {
  return {
    id: "a1",
    run_id: "run-1",
    agent_type: "NETWORK",
    status: "COMPLETED",
    task: "Pick a route",
    elapsed_ms: 4200,
    total_tokens: 1800,
    created_at: "2026-10-15T10:00:05Z",
    recommendation: {
      route: "BOM-DEL",
      action: "INCREASE_FREQUENCY",
      expected_profit_impact: 85_000,
      confidence: 0.82,
      risks: [],
      reasoning: "Demand exceeds capacity.",
      cited_sources: ["fuel:eia:2026-10-10"],
    },
    ...patch,
  };
}

export function makeIteration(patch: Partial<RunIteration> = {}): RunIteration {
  return {
    id: "it-1",
    run_id: "run-1",
    sequence: 1,
    objective: "Improve airline profitability",
    status: "COMPLETED",
    created_at: "2026-10-15T10:00:00Z",
    completed_at: "2026-10-15T10:00:40Z",
    agent_executions: [makeAgent()],
    decision: makeDecision(),
    ...patch,
  };
}

export function makeRunDetail(patch: Partial<RunDetail> = {}): RunDetail {
  const iteration = makeIteration();
  return {
    id: "run-1",
    objective: "Improve airline profitability",
    status: "COMPLETED",
    created_at: "2026-10-15T10:00:00Z",
    completed_at: "2026-10-15T10:00:40Z",
    agent_executions: iteration.agent_executions,
    decision: iteration.decision,
    iterations: [iteration],
    ...patch,
  };
}

export function makeEvidenceItem(patch: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    id: "fuel:eia:2026-10-10",
    source: "eia_jet_fuel",
    kind: "dataset",
    title: "Jet fuel, US Gulf Coast",
    url: "https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm",
    fetched_at: "2026-10-14T00:00:00Z",
    reliability: 0.9,
    content: { usd_per_gallon: 2.31 },
    ...patch,
  };
}

export function makeEvidence(): RunEvidenceEntry[] {
  return [
    {
      agent_execution_id: "a1",
      agent_type: "NETWORK",
      iteration: 1,
      evidence: [
        makeEvidenceItem(),
        makeEvidenceItem({
          id: "web:3f9a1c2e",
          source: "web",
          kind: "web",
          title: "Air traffic demand India 2026",
          url: "https://example.com/news",
          reliability: 0.4,
          content: { snippet: "Demand is up.", engine: "duckduckgo", query: "DEL BOM air traffic demand India 2026" },
        }),
      ],
      evidence_unavailable: ["dgca_market: no data"],
      cited_sources: ["fuel:eia:2026-10-10"],
    },
  ];
}

export function makeDatasets(): DatasetInfo[] {
  return [
    {
      source: "openflights",
      title: "OpenFlights routes",
      description: "Rival airlines per route.",
      license: "ODbL 1.0 (OpenFlights)",
      source_url: "https://openflights.org/data.html",
      latest: { status: "SUCCESS", fetched_at: "2026-10-14T08:00:00Z", row_count: 120, error: null },
    },
    {
      source: "eia_jet_fuel",
      title: "EIA jet fuel",
      description: "US Gulf Coast kerosene-type jet fuel.",
      license: "Public domain (US EIA)",
      source_url: "https://www.eia.gov/",
      latest: { status: "FAILED", fetched_at: "2026-10-14T08:01:00Z", row_count: 0, error: "timeout" },
    },
    {
      source: "fx",
      title: "USD/INR",
      description: "Frankfurter daily rates.",
      license: "ECB reference rates",
      source_url: "https://frankfurter.dev/",
      latest: null,
    },
    {
      source: "dgca",
      title: "DGCA domestic traffic",
      description: "Monthly Indian domestic traffic.",
      license: "Government of India",
      source_url: "https://www.dgca.gov.in/",
      latest: { status: "FALLBACK", fetched_at: "2026-10-14T08:02:00Z", row_count: 6, error: null },
    },
  ];
}

export function makeMarketRoutes(): MarketRoute[] {
  return [
    { airline_code: "6E", airline_name: "IndiGo", origin: "DEL", destination: "BOM", stops: 0, equipment: "320 321" },
    { airline_code: "AI", airline_name: null, origin: "DEL", destination: "BOM", stops: 0, equipment: "" },
    { airline_code: "UK", airline_name: "Vistara", origin: "BOM", destination: "DEL", stops: 1, equipment: "320" },
  ];
}

export function makeDgca(): DgcaTrafficRow[] {
  return [
    { period: "2026-08", airline: "IndiGo", passengers: 8_000_000, market_share_pct: 62.1, load_factor_pct: 88.4, is_fallback: false },
    { period: "2026-08", airline: "Air India", passengers: null, market_share_pct: null, load_factor_pct: null, is_fallback: true },
  ];
}

export function makeWeights(): DecisionWeightsResponse {
  return { ...structuredClone(DEFAULT_WEIGHTS), updated_at: "2026-10-15T09:00:00Z" };
}

export function makeSearch(patch: Partial<WebSearchResponse> = {}): WebSearchResponse {
  return {
    query: "india aviation",
    cached: false,
    stale: false,
    fetched_at: "2026-10-15T10:00:00Z",
    results: [
      { title: "Result one", url: "https://example.com/1", snippet: "First snippet", engine: "duckduckgo" },
      { title: "Result two", url: "javascript:alert(1)", snippet: "Bad link", engine: "bing" },
    ],
    ...patch,
  };
}

/** One happy-path handler per endpoint the UI calls on any page. */
export function defaultHandlers(): HttpHandler[] {
  return [
    http.get(api("/api/stats"), () => HttpResponse.json(makeStats())),
    http.get(api("/api/stats/runs"), () => HttpResponse.json([makeStatsRun()])),
    http.get(api("/api/runs"), () => HttpResponse.json([])),
    http.get(api("/api/runs/:id"), () => HttpResponse.json(makeRunDetail())),
    http.get(api("/api/runs/:id/evidence"), () => HttpResponse.json(makeEvidence())),
    http.get(api("/api/runs/:id/messages"), () => HttpResponse.json([])),
    http.get(api("/api/runs/:id/graph"), () => HttpResponse.json({ nodes: [], edges: [] })),
    http.get(api("/api/runs/:id/knowledge-graph"), () => HttpResponse.json({ nodes: [], edges: [] })),
    http.get(api("/api/events"), () => HttpResponse.json([])),
    http.get(api("/api/datasets"), () => HttpResponse.json(makeDatasets())),
    http.post(api("/api/datasets/refresh"), () =>
      HttpResponse.json([
        { source: "openflights", status: "SUCCESS", row_count: 120, error: null, fetched_at: "2026-10-15T10:00:00Z" },
      ]),
    ),
    http.get(api("/api/datasets/fuel-prices"), () =>
      HttpResponse.json([
        { date: "2026-10-08", usd_per_gallon: 2.2 },
        { date: "2026-10-09", usd_per_gallon: 2.28 },
        { date: "2026-10-10", usd_per_gallon: 2.31 },
      ]),
    ),
    http.get(api("/api/datasets/fx-rates"), () =>
      HttpResponse.json([
        { date: "2026-10-13", rate: 83.1 },
        { date: "2026-10-14", rate: 83.42 },
      ]),
    ),
    http.get(api("/api/datasets/market-routes"), () => HttpResponse.json(makeMarketRoutes())),
    http.get(api("/api/datasets/dgca-traffic"), () => HttpResponse.json(makeDgca())),
    http.get(api("/api/web-search/status"), () => HttpResponse.json({ enabled: true, configured: true, reachable: true })),
    http.get(api("/api/web-search/cache"), () =>
      HttpResponse.json([{ query: "india aviation", result_count: 2, fetched_at: "2026-10-15T10:00:00Z", results: makeSearch().results }]),
    ),
    http.post(api("/api/web-search"), () => HttpResponse.json(makeSearch())),
    http.get(api("/api/decision-weights"), () => HttpResponse.json(makeWeights())),
    http.put(api("/api/decision-weights"), async ({ request }) =>
      HttpResponse.json({ ...(await request.json()), updated_at: "2026-10-15T11:00:00Z" }),
    ),
  ];
}
