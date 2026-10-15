// Response types for evidence, datasets, web search, decision weights and stats
// (design spec §2.6, §3, §4, §5). Type-only: erased at compile time, so it is excluded from
// coverage together with the rest of src/types/**.
import type { OrchestrationRunStatus } from "./index";

export type Verdict = "RECOMMEND" | "REVIEW" | "REJECT";

export type EvidenceSource = "openflights" | "eia_jet_fuel" | "fx" | "dgca" | "web";

export interface EvidenceItem {
  id: string;
  source: EvidenceSource;
  kind: "dataset" | "web";
  title: string;
  url: string | null;
  fetched_at: string | null;
  // 0..1 — how much the decision engine trusts this source.
  reliability: number;
  content: Record<string, unknown> | string;
}

/** GET /api/runs/{id}/evidence, one entry per agent execution in execution order. */
export interface RunEvidenceEntry {
  agent_execution_id: string;
  agent_type: string;
  iteration: number;
  evidence: EvidenceItem[];
  evidence_unavailable: string[];
  cited_sources: string[];
}

export interface ScoreBreakdownEntry {
  weight: number;
  value: number;
  contribution: number;
}

/** What `Decision.validation_result` holds. Decisions created before the weighted engine lack
 * score, verdict, warnings and score_breakdown, so every field is optional. */
export interface DecisionValidation {
  risk?: string;
  constraints?: string;
  conflicts?: string[];
  warnings?: string[];
  score?: number;
  verdict?: Verdict;
  score_breakdown?: Record<string, ScoreBreakdownEntry>;
}

export type DatasetStatus = "SUCCESS" | "FAILED" | "FALLBACK";

export interface DatasetInfo {
  source: string;
  title: string;
  description: string;
  license: string;
  source_url: string;
  latest: {
    status: DatasetStatus;
    fetched_at: string;
    row_count: number;
    error: string | null;
  } | null;
}

export interface DatasetRefreshResult {
  source: string;
  status: DatasetStatus;
  row_count: number;
  error: string | null;
  fetched_at: string;
}

export interface FuelPricePoint {
  date: string;
  usd_per_gallon: number;
}

export interface FxRatePoint {
  date: string;
  rate: number;
}

export interface MarketRoute {
  airline_code: string;
  airline_name: string | null;
  origin: string;
  destination: string;
  stops: number;
  equipment: string;
}

export interface DgcaTrafficRow {
  period: string;
  airline: string;
  passengers: number | null;
  market_share_pct: number | null;
  load_factor_pct: number | null;
  is_fallback: boolean;
}

export interface WebSearchStatus {
  enabled: boolean;
  configured: boolean;
  reachable: boolean;
}

export interface WebSearchResult {
  title: string;
  url: string;
  snippet: string;
  engine: string;
}

export interface WebSearchResponse {
  query: string;
  cached: boolean;
  stale: boolean;
  fetched_at: string | null;
  results: WebSearchResult[];
}

export interface WebSearchCacheEntry {
  query: string;
  result_count: number;
  fetched_at: string;
  results: WebSearchResult[];
}

export type WeightFactor = "profit" | "confidence" | "feasibility" | "risk" | "data_quality";
export type WeightAgent = "NETWORK" | "FLEET" | "MAINTENANCE" | "CREW" | "CARGO";

export interface DecisionWeights {
  factors: Record<WeightFactor, number>;
  agent_confidence: Record<WeightAgent, number>;
  thresholds: { recommend: number; review: number };
  profit_scale_usd: number;
}

/** GET /api/decision-weights; PUT sends the same shape without `updated_at`. */
export interface DecisionWeightsResponse extends DecisionWeights {
  updated_at?: string | null;
}

export interface Stats {
  runs_total: number;
  runs_completed: number;
  runs_failed: number;
  runs_running: number;
  p95_run_duration_ms: number | null;
  tokens_total: number;
  tokens_last_24h: number;
  decisions_by_verdict: Record<Verdict, number>;
  latest_fuel_price: { date: string; usd_per_gallon: number } | null;
  latest_usd_inr: { date: string; rate: number } | null;
  runs_per_day: { date: string; count: number }[];
  tokens_per_day: { date: string; tokens: number }[];
}

export interface StatsRun {
  id: string;
  objective: string;
  status: OrchestrationRunStatus;
  created_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  total_tokens: number | null;
  iterations: number;
  decision: {
    summary: string;
    verdict: Verdict | null;
    score: number | null;
    expected_profit_impact: number;
    risk: string | null;
  } | null;
}
