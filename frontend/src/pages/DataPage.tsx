import { useState, type FormEvent } from "react";
import { MAX_SEARCH_QUERY_LENGTH, useWebSearch, useWebSearchCache, useWebSearchStatus } from "../api/useWebSearch";
import { useAirworthinessDirectives, useBrentPrices, useDatasets, useFuelPrices, useFxRates, useRefreshDatasets, useWeather, useWorldBank } from "../api/useDatasets";
import { LineChart } from "../components/charts/LineChart";
import { Badge, type BadgeTone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel } from "../components/ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import type { AirportWeather, DatasetInfo, DatasetStatus, FlightCategory, ForecastDay, WebSearchResult } from "../types/api";
import { safeHref, sourceLabel } from "../utils/evidence";
import { formatDay, formatDateTime, formatFuelPrice, formatNumber, formatRate } from "../utils/format";

const STATUS_TONE: Record<DatasetStatus, BadgeTone> = { SUCCESS: "ok", FALLBACK: "warn", FAILED: "bad" };
const STATUS_HELP: Record<DatasetStatus, string> = {
  SUCCESS: "The last refresh fetched fresh data.",
  FALLBACK: "The live source was unavailable, so a bundled snapshot is in use.",
  FAILED: "The last refresh failed. Rows from the last good refresh are kept.",
};

const rows = (count: number) => `${count} ${count === 1 ? "row" : "rows"}`;

function StatusBadge({ status }: { status: DatasetStatus }) {
  return (
    <Badge tone={STATUS_TONE[status] ?? "muted"} title={STATUS_HELP[status]}>
      {status}
    </Badge>
  );
}

/** The latest fuel price or exchange rate with a small history, for the sources that have one. */
function LatestValue({ source }: { source: string }) {
  const isFuel = source === "eia_jet_fuel";
  const isFx = source === "fx";
  const isBrent = source === "eia_brent";
  const fuel = useFuelPrices(90);
  const fx = useFxRates(90, "INR");
  const brent = useBrentPrices(90);
  if (!isFuel && !isFx && !isBrent) return null;
  const query = isFuel ? fuel : isBrent ? brent : fx;
  if (query.isLoading) return <LoadingState label="Loading series…" />;
  if (query.isError) return <p className="text-xs text-bad">Could not load the series.</p>;
  const data = isFuel
    ? (fuel.data ?? []).map((p) => ({ x: p.date, y: p.usd_per_gallon }))
    : isBrent
      ? (brent.data ?? []).map((p) => ({ x: p.date, y: p.usd_per_barrel }))
      : (fx.data ?? []).map((p) => ({ x: p.date, y: p.rate }));
  if (data.length === 0) {
    return <p className="text-xs text-muted">{isFx ? "No rates stored yet" : "No prices stored yet"}</p>;
  }
  const money = (v: number) => (isBrent ? `$${v.toFixed(2)}` : isFuel ? formatFuelPrice(v) : formatRate(v));
  const unit = isFuel ? "USD per gallon" : isBrent ? "USD per barrel" : "INR per USD";
  const title = isFuel ? "Jet fuel price, last 90 days" : isBrent ? "Brent crude price, last 90 days" : "USD to INR rate, last 90 days";
  const last = data[data.length - 1];
  return (
    <div className="mt-2">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-lg font-semibold text-ink-strong">
          {money(last.y)}
        </span>
        <span className="text-xs text-muted">
          {unit} on {formatDay(last.x)}
        </span>
      </div>
      <LineChart
        data={data}
        label={title}
        tone={isFuel || isBrent ? "ok" : "accent"}
        height={110}
        formatX={formatDay}
        formatY={money}
      />
    </div>
  );
}

function DatasetCard({
  dataset,
  onRefresh,
  refreshing,
}: {
  dataset: DatasetInfo;
  onRefresh: (source: string) => void;
  refreshing: boolean;
}) {
  const { latest } = dataset;
  const href = safeHref(dataset.source_url);
  return (
    <Panel
      title={dataset.title}
      data-testid={`dataset-${dataset.source}`}
      actions={
        <Button variant="ghost" disabled={refreshing} onClick={() => onRefresh(dataset.source)} aria-label="Refresh" title={`Refresh ${dataset.title}`}>
          Refresh
        </Button>
      }
    >
      <p className="text-sm text-muted">{dataset.description}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        {latest ? (
          <>
            <StatusBadge status={latest.status} />
            <span className="font-mono text-ink">{rows(latest.row_count)}</span>
            <span className="text-muted">Refreshed {formatDateTime(latest.fetched_at)}</span>
          </>
        ) : (
          <Badge tone="muted">Never refreshed</Badge>
        )}
      </div>
      {latest?.error && <p className="mt-1 break-words text-xs text-bad">{latest.error}</p>}
      <LatestValue source={dataset.source} />
      <p className="mt-2 break-words text-2xs text-faint">
        {dataset.license}
        {href && (
          <>
            {" · "}
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
              Source
            </a>
          </>
        )}
      </p>
    </Panel>
  );
}

function DatasetsSection() {
  const { data, isLoading, isError, error, refetch } = useDatasets();
  const refresh = useRefreshDatasets();
  const busy = refresh.isPending;

  return (
    <>
      <PageHeader
        title="Data"
        subtitle="External datasets the agents use as evidence, and the web search that supplements them."
        actions={
          <Button disabled={busy} onClick={() => refresh.mutate(undefined)}>
            {busy ? "Refreshing…" : "Refresh all"}
          </Button>
        }
      />
      {refresh.isError && <ErrorState title="Refresh failed" error={refresh.error} />}
      {refresh.isSuccess && (
        <div className="mb-3 rounded-sm border border-line bg-panel px-3 py-2 text-sm" data-testid="refresh-result">
          <div className="label text-muted">Last refresh</div>
          <ul className="mt-1 space-y-0.5">
            {refresh.data.map((result) => (
              <li key={result.source} className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-ink" title={sourceLabel(result.source)}>{result.source}</span>
                <StatusBadge status={result.status} />
                <span className="text-muted">{rows(result.row_count)}</span>
                {result.error && <span className="break-words text-bad">{result.error}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {isLoading && <LoadingState label="Loading datasets…" />}
      {isError && <ErrorState title="Could not load the datasets" error={error} onRetry={() => void refetch()} />}
      {data && data.length === 0 && <EmptyState title="No datasets are registered" hint="The backend reports no data sources." />}
      {data && data.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          {data.map((dataset) => (
            <DatasetCard key={dataset.source} dataset={dataset} onRefresh={(source) => refresh.mutate([source])} refreshing={busy} />
          ))}
        </div>
      )}
    </>
  );
}

const CATEGORY_TONE: Record<FlightCategory, BadgeTone> = {
  VFR: "ok",
  MVFR: "accent",
  IFR: "warn",
  LIFR: "bad",
  UNKNOWN: "muted",
};
const HEAVY_RAIN_MM = 20;
const HIGH_GUST_KMH = 60;

/** The reasons a forecast day is disruptive, in order of severity. */
export function forecastFlags(day: ForecastDay): string[] {
  const flags: string[] = [];
  if (day.thunderstorm) flags.push("thunderstorm");
  if (day.precipitation_mm >= HEAVY_RAIN_MM) flags.push("heavy rain");
  if (day.max_gust_kmh >= HIGH_GUST_KMH) flags.push("high gusts");
  return flags;
}

const orDash = (value: number | null, unit: string) => (value === null ? "—" : `${value} ${unit}`);

function ForecastStrip({ forecast }: { forecast: ForecastDay[] }) {
  if (forecast.length === 0) return <p className="text-xs text-muted">No forecast stored</p>;
  return (
    <ul className="flex gap-1" aria-label="7-day forecast">
      {forecast.map((day) => {
        const flags = forecastFlags(day);
        const title = `${formatDay(day.date)}: ${day.precipitation_mm} mm rain, gusts ${day.max_gust_kmh} km/h${flags.length ? ` (${flags.join(", ")})` : ""}`;
        return (
          <li
            key={day.date}
            title={title}
            data-flagged={flags.length > 0}
            className={`flex min-w-0 flex-1 flex-col items-center rounded-sm border px-1 py-0.5 text-2xs ${
              flags.length ? "border-warn/40 bg-warn/10 text-warn" : "border-line text-muted"
            }`}
          >
            <span>{formatDay(day.date)}</span>
            <span className="font-mono">{flags.length ? flags.map((f) => (f === "thunderstorm" ? "TS" : f === "heavy rain" ? "RN" : "GU")).join(" ") : "ok"}</span>
          </li>
        );
      })}
    </ul>
  );
}

function AirportCard({ airport }: { airport: AirportWeather }) {
  return (
    <li className="rounded-sm border border-line p-2" data-testid={`weather-${airport.airport}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-ink-strong">{airport.airport}</span>
        <span className="font-mono text-xs text-muted">{airport.icao}</span>
        <Badge tone={CATEGORY_TONE[airport.flight_category] ?? "muted"}>{airport.flight_category}</Badge>
        <span className="text-xs text-muted">Observed {airport.observed_at ? formatDateTime(airport.observed_at) : "—"}</span>
      </div>
      <dl className="mt-1 grid grid-cols-2 gap-x-3 text-sm sm:grid-cols-4">
        <div><dt className="label text-muted">Wind</dt><dd className="font-mono">{orDash(airport.wind_kt, "kt")}</dd></div>
        <div><dt className="label text-muted">Gust</dt><dd className="font-mono">{orDash(airport.gust_kt, "kt")}</dd></div>
        <div><dt className="label text-muted">Visibility</dt><dd className="font-mono">{orDash(airport.visibility_sm, "SM")}</dd></div>
        <div><dt className="label text-muted">Ceiling</dt><dd className="font-mono">{orDash(airport.ceiling_ft, "ft")}</dd></div>
      </dl>
      {(airport.taf_worst_flight_category_24h || airport.taf_thunderstorm_24h != null) && (
        <p className="mt-1 text-xs text-muted" data-testid={`taf-${airport.airport}`}>
          TAF next 24h: worst {airport.taf_worst_flight_category_24h ?? "—"}
          {airport.taf_thunderstorm_24h ? <span className="ml-1 font-semibold text-warn">TS</span> : null}
        </p>
      )}
      {airport.raw_text && <p className="mt-1 break-words font-mono text-2xs text-faint">{airport.raw_text}</p>}
      <div className="mt-2">
        <ForecastStrip forecast={airport.forecast} />
      </div>
    </li>
  );
}

function WeatherSection() {
  const { data, isLoading, isError, error, refetch } = useWeather();
  return (
    <Panel title="Airport weather" className="mt-3" data-testid="weather-panel">
      {isLoading && <LoadingState label="Loading weather…" />}
      {isError && <ErrorState title="Could not load the weather" error={error} onRetry={() => void refetch()} />}
      {data && data.length === 0 && <EmptyState title="No weather stored yet" hint="Refresh the aviation_weather and open_meteo sources." />}
      {data && data.length > 0 && (
        <>
          <ul className="grid gap-2 md:grid-cols-2">
            {data.map((airport) => (
              <AirportCard key={airport.icao} airport={airport} />
            ))}
          </ul>
          <p className="mt-2 text-2xs text-faint">Forecast flags: TS thunderstorm, RN rain of {HEAVY_RAIN_MM} mm or more, GU gusts of {HIGH_GUST_KMH} km/h or more.</p>
        </>
      )}
    </Panel>
  );
}

function MacroSection() {
  const { data, isLoading, isError, error, refetch } = useWorldBank();
  return (
    <Panel title="Macro indicators" className="mt-3" data-testid="macro-panel">
      {isLoading && <LoadingState label="Loading indicators…" />}
      {isError && <ErrorState title="Could not load the indicators" error={error} onRetry={() => void refetch()} />}
      {data && data.length === 0 && <EmptyState title="No indicators stored yet" hint="Refresh the world_bank source." />}
      {data && data.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-3">
          {data.map((row) => (
            <li key={row.indicator} className="rounded-sm border border-line p-2" data-testid={`macro-${row.indicator}`}>
              <div className="label text-muted">{row.label}</div>
              <div className="font-mono text-lg font-semibold text-ink-strong">
                {formatNumber(row.value)} <span className="text-xs font-normal text-muted">{row.unit} ({row.year})</span>
              </div>
              {row.yoy_pct === null ? (
                <span className="text-xs text-muted">YoY —</span>
              ) : (
                <span className={`text-xs ${row.yoy_pct > 0 ? "text-ok" : row.yoy_pct < 0 ? "text-bad" : "text-muted"}`} data-testid="yoy">
                  YoY {row.yoy_pct > 0 ? "+" : ""}
                  {row.yoy_pct.toFixed(1)}%
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function DirectivesSection() {
  const { data, isLoading, isError, error, refetch } = useAirworthinessDirectives();
  return (
    <Panel title="Airworthiness directives" className="mt-3" data-testid="directives-panel">
      {isLoading && <LoadingState label="Loading directives…" />}
      {isError && <ErrorState title="Could not load the directives" error={error} onRetry={() => void refetch()} />}
      {data && data.length === 0 && <EmptyState title="No directives stored yet" hint="Refresh the faa_airworthiness_directives source." />}
      {data && data.length > 0 && (
        <ul className="divide-y divide-line">
          {data.slice(0, 10).map((ad) => {
            const href = safeHref(ad.html_url);
            return (
              <li key={ad.document_number} className="py-2">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-mono text-xs text-muted">{formatDay(ad.publication_date)}</span>
                  {href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer" className="break-words text-accent hover:underline">
                      {ad.title}
                    </a>
                  ) : (
                    <span className="break-words text-ink-strong">{ad.title}</span>
                  )}
                </div>
                {ad.aircraft_types.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {ad.aircraft_types.map((type) => (
                      <Badge key={type} tone="muted">{type}</Badge>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

function ResultList({ results }: { results: WebSearchResult[] }) {
  return (
    <ul className="divide-y divide-line">
      {results.map((result) => {
        const href = safeHref(result.url);
        return (
          <li key={`${result.url}-${result.title}`} className="py-2">
            {href ? (
              <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="break-words font-medium text-accent hover:underline">
                {result.title}
              </a>
            ) : (
              <span className="break-words font-medium text-ink-strong">{result.title}</span>
            )}
            <div className="break-words text-xs text-muted">{result.snippet}</div>
            <div className="text-2xs text-faint">{result.engine}</div>
          </li>
        );
      })}
    </ul>
  );
}

function StatusFlag({ label, on }: { label: string; on: boolean }) {
  return (
    <Badge tone={on ? "ok" : "bad"}>
      {on ? "" : "Not "}
      {label}
    </Badge>
  );
}

function WebSearchSection() {
  const [query, setQuery] = useState("");
  const status = useWebSearchStatus();
  const cache = useWebSearchCache();
  const search = useWebSearch();

  const active = Boolean(status.data?.enabled && status.data.configured);
  const trimmed = query.trim();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (active && trimmed) search.mutate(trimmed);
  };

  return (
    <Panel title="Web search" className="mt-3">
      <div data-testid="web-search-status" className="mb-3">
        {status.isLoading && <LoadingState label="Checking web search…" />}
        {status.isError && <ErrorState title="Could not load the web search status" error={status.error} onRetry={() => void status.refetch()} />}
        {status.data && (
          <div className="flex flex-wrap items-center gap-2">
            <StatusFlag label="Enabled" on={status.data.enabled} />
            <StatusFlag label="Configured" on={status.data.configured} />
            <StatusFlag label="Reachable" on={status.data.reachable} />
          </div>
        )}
        {status.data && !active && (
          <p className="mt-2 text-sm text-muted">
            Web search is not available: turn it on and point it at a SearXNG instance in the backend settings.
          </p>
        )}
        {status.data && active && !status.data.reachable && (
          <p className="mt-2 text-sm text-warn">The search engine cannot be reached right now. Cached results are still used.</p>
        )}
      </div>

      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <div className="flex min-w-[220px] flex-1 flex-col gap-1">
          <label htmlFor="web-search-query" className="label text-muted">
            Search query
          </label>
          <input
            id="web-search-query"
            className="field"
            value={query}
            maxLength={MAX_SEARCH_QUERY_LENGTH}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. India domestic aviation demand"
            disabled={!active}
          />
        </div>
        <Button type="submit" disabled={!active || !trimmed || search.isPending}>
          {search.isPending ? "Searching…" : "Search"}
        </Button>
      </form>

      <div className="mt-3" aria-live="polite">
        {search.isError && <ErrorState title="Search failed" error={search.error} />}
        {search.isSuccess && (
          <div data-testid="web-search-results">
            <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span>
                {search.data.results.length} {search.data.results.length === 1 ? "result" : "results"} for “{search.data.query}”
              </span>
              <span>fetched {formatDateTime(search.data.fetched_at)}</span>
              {search.data.cached && <Badge tone="muted">cached</Badge>}
              {search.data.stale && <Badge tone="warn" title="The engine failed, so an expired cache entry is shown.">stale</Badge>}
            </div>
            {search.data.results.length === 0 ? <EmptyState title="No results for this query" /> : <ResultList results={search.data.results} />}
          </div>
        )}
      </div>

      <div className="mt-4" data-testid="web-search-cache">
        <h3 className="label mb-1 text-muted">Cached queries</h3>
        {cache.isLoading && <LoadingState label="Loading cached queries…" />}
        {cache.isError && <ErrorState title="Could not load the cached queries" error={cache.error} onRetry={() => void cache.refetch()} />}
        {cache.data && cache.data.length === 0 && <EmptyState title="No queries cached yet" hint="Agents and manual searches fill this list." />}
        {cache.data && cache.data.length > 0 && (
          <ul className="divide-y divide-line">
            {cache.data.map((entry) => (
              <li key={entry.query} className="flex flex-wrap items-center justify-between gap-2 py-1.5 text-sm">
                <div className="min-w-0">
                  <span className="break-words text-ink">{entry.query}</span>
                  <span className="ml-2 text-xs text-muted">
                    {entry.result_count} {entry.result_count === 1 ? "result" : "results"} · {formatDateTime(entry.fetched_at)}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  disabled={!active || search.isPending}
                  aria-label={`Run again: ${entry.query}`}
                  onClick={() => {
                    setQuery(entry.query);
                    search.mutate(entry.query);
                  }}
                >
                  Run again
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}

export function DataPage() {
  return (
    <div>
      <DatasetsSection />
      <WeatherSection />
      <MacroSection />
      <DirectivesSection />
      <WebSearchSection />
    </div>
  );
}
