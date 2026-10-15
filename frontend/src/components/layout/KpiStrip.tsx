import type { ReactNode } from "react";
import { useFuelPrices } from "../../api/useDatasets";
import { useStats } from "../../api/useStats";
import { useConnectionStore } from "../../stores/connectionStore";
import { useDebugStore } from "../../stores/debugStore";
import { formatCompact, formatDuration, formatFuelPrice, formatNumber, formatRate } from "../../utils/format";
import { Sparkline, type Tone } from "../charts/Sparkline";
import { Pulse } from "../ui/Pulse";
import { Tooltip } from "../ui/Tooltip";

export function KpiTile({
  label,
  value,
  hint,
  tone,
  spark,
}: {
  label: string;
  value: string;
  hint: string;
  tone?: Tone;
  spark?: ReactNode;
}) {
  return (
    <Tooltip content={hint}>
      <div
        tabIndex={0}
        data-testid={`kpi-${label}`}
        className="flex min-w-[112px] items-center gap-2 rounded-sm border border-line bg-canvas px-2.5 py-1.5"
      >
        <div className="min-w-0">
          <div className="label text-muted">{label}</div>
          <div
            className={`font-mono text-base font-semibold leading-5 ${
              tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : "text-ink-strong"
            }`}
          >
            {value}
          </div>
        </div>
        {spark}
      </div>
    </Tooltip>
  );
}

const CONNECTION: Record<string, { label: string; color: string; dot: string }> = {
  open: { label: "Live", color: "text-ok", dot: "bg-ok" },
  connecting: { label: "Connecting", color: "text-warn", dot: "bg-warn" },
  closed: { label: "Disconnected", color: "text-bad", dot: "bg-bad" },
};

export function ConnectionIndicator() {
  const status = useConnectionStore((state) => state.status);
  const view = CONNECTION[status] ?? CONNECTION.closed;
  return (
    <Tooltip content={status === "open" ? "Receiving live events over the WebSocket." : "Live updates are paused; the app retries automatically."}>
      <span
        role="status"
        tabIndex={0}
        aria-label={`Event stream: ${view.label}`}
        className={`flex items-center gap-1.5 text-xs font-medium ${view.color}`}
      >
        {status === "open" ? (
          <Pulse active className={view.dot} />
        ) : (
          <span aria-hidden="true" className={`inline-block h-1.5 w-1.5 rounded-full ${view.dot}`} />
        )}
        {view.label}
      </span>
    </Tooltip>
  );
}

export function DebugToggle() {
  const enabled = useDebugStore((state) => state.enabled);
  const toggle = useDebugStore((state) => state.toggle);
  return (
    <Tooltip content="Debug mode shows raw payloads and LLM responses in the inspector and event tables.">
      <button
        type="button"
        aria-pressed={enabled}
        onClick={toggle}
        className={`rounded-sm border px-2 py-1 text-xs font-medium ${
          enabled ? "border-accent bg-accent-subtle text-accent" : "border-line-strong text-muted hover:text-ink"
        }`}
      >
        Debug {enabled ? "on" : "off"}
      </button>
    </Tooltip>
  );
}

/** The top bar: headline KPIs from /api/stats, then the event-stream status and Debug toggle. */
export function KpiStrip() {
  const { data: stats, isError, refetch } = useStats();
  const { data: fuel } = useFuelPrices(30);

  const runsSpark = stats?.runs_per_day.map((d) => d.count) ?? [];
  const tokensSpark = stats?.tokens_per_day.map((d) => d.tokens) ?? [];
  const fuelSpark = fuel?.map((point) => point.usd_per_gallon) ?? [];
  const failed = stats?.runs_failed ?? 0;

  return (
    <header className="flex flex-wrap items-center gap-2 border-b border-line bg-panel px-3 py-2">
      <span className="mr-2 text-sm font-semibold text-ink-strong">AeroTwin AI</span>
      <div className="flex flex-1 flex-wrap items-center gap-2" aria-label="Key metrics" role="group">
        <KpiTile
          label="Runs"
          value={formatNumber(stats?.runs_total)}
          hint="Total orchestration runs, with runs per day over the last 14 days."
          spark={<Sparkline values={runsSpark} label="Runs per day, last 14 days" />}
        />
        <KpiTile
          label="Failed"
          value={formatNumber(stats?.runs_failed)}
          hint="Runs that ended in FAILED."
          tone={failed > 0 ? "bad" : undefined}
        />
        <KpiTile
          label="p95 time"
          value={formatDuration(stats?.p95_run_duration_ms)}
          hint="95th percentile of run duration. A dash means no run has finished yet."
        />
        <KpiTile
          label="Tokens 24h"
          value={formatCompact(stats?.tokens_last_24h)}
          hint="LLM tokens used in the last 24 hours, with daily usage over the last 14 days."
          spark={<Sparkline values={tokensSpark} label="Tokens per day, last 14 days" tone="warn" />}
        />
        <KpiTile
          label="Jet fuel"
          value={formatFuelPrice(stats?.latest_fuel_price?.usd_per_gallon)}
          hint={
            stats && !stats.latest_fuel_price
              ? "No fuel price yet. Refresh the datasets on the Data page."
              : "Latest US Gulf Coast jet fuel price (EIA), with the last 30 days."
          }
          spark={<Sparkline values={fuelSpark} label="Jet fuel price, last 30 days" tone="ok" />}
        />
        <KpiTile
          label="USD/INR"
          value={formatRate(stats?.latest_usd_inr?.rate)}
          hint={
            stats && !stats.latest_usd_inr
              ? "No exchange rate yet. Refresh the datasets on the Data page."
              : "Latest USD to INR rate (Frankfurter)."
          }
        />
        {isError && (
          <button
            type="button"
            onClick={() => void refetch()}
            className="rounded-sm border border-bad/40 px-2 py-1 text-xs text-bad hover:bg-bad/10"
          >
            Stats unavailable. Retry
          </button>
        )}
      </div>
      <div className="flex items-center gap-3">
        <ConnectionIndicator />
        <DebugToggle />
      </div>
    </header>
  );
}
