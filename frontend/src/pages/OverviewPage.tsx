import { Link } from "react-router-dom";
import { useStats, useStatsRuns } from "../api/useStats";
import { Sparkline, type Tone } from "../components/charts/Sparkline";
import { StackedBar } from "../components/charts/BreakdownBars";
import { ActivityFeed } from "../components/dashboard/ActivityFeed";
import { RunsTable } from "../components/run/RunsTable";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel } from "../components/ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { formatCompact, formatNumber } from "../utils/format";
import type { Stats } from "../types/api";

function Tile({
  label,
  value,
  caption,
  values,
  tone = "accent",
}: {
  label: string;
  value: string;
  caption: string;
  values?: number[];
  tone?: Tone;
}) {
  return (
    <div className="rounded-sm border border-line bg-panel px-3 py-2" data-testid={`tile-${label}`}>
      <div className="label text-muted">{label}</div>
      <div className="mt-0.5 flex items-end justify-between gap-2">
        <div className="font-mono text-2xl font-semibold text-ink-strong">{value}</div>
        {values && <Sparkline values={values} width={110} height={34} tone={tone} label={`${label}, last 14 days`} />}
      </div>
      <div className="mt-0.5 text-xs text-muted">{caption}</div>
    </div>
  );
}

function lastOf(series: { count?: number; tokens?: number }[] | undefined, key: "count" | "tokens"): number | undefined {
  return series && series.length > 0 ? series[series.length - 1][key] : undefined;
}

function Tiles({ stats }: { stats: Stats }) {
  const runs = stats.runs_per_day.map((d) => d.count);
  const tokens = stats.tokens_per_day.map((d) => d.tokens);
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      <Tile
        label="Runs per day"
        value={formatNumber(lastOf(stats.runs_per_day, "count") ?? 0)}
        caption={`${formatNumber(stats.runs_total)} runs in total`}
        values={runs}
      />
      <Tile
        label="Tokens per day"
        value={formatCompact(lastOf(stats.tokens_per_day, "tokens") ?? 0)}
        caption={`${formatCompact(stats.tokens_total)} tokens in total`}
        values={tokens}
        tone="warn"
      />
      <Tile label="In flight" value={formatNumber(stats.runs_running)} caption={`${formatNumber(stats.runs_completed)} completed`} tone="ok" />
      <Tile
        label="Failed"
        value={formatNumber(stats.runs_failed)}
        caption={stats.runs_failed > 0 ? "Open the Runs page and filter by Failed" : "No failures"}
        tone="bad"
      />
    </div>
  );
}

export function OverviewPage() {
  const stats = useStats();
  const runs = useStatsRuns(10);
  const verdicts = stats.data?.decisions_by_verdict;
  const decided = verdicts ? verdicts.RECOMMEND + verdicts.REVIEW + verdicts.REJECT : 0;

  return (
    <div data-testid="page-content">
      <PageHeader
        title="Overview"
        subtitle="How the platform is doing: activity, decision outcomes and what is happening right now."
      />
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-3">
          {stats.isLoading ? (
            <LoadingState label="Loading statistics…" />
          ) : stats.isError || !stats.data ? (
            <ErrorState title="Could not load statistics" error={stats.error} onRetry={() => void stats.refetch()} />
          ) : (
            <Tiles stats={stats.data} />
          )}

          <Panel title="Decisions by verdict">
            {stats.data ? (
              decided === 0 ? (
                <p className="text-sm text-muted" data-testid="verdicts-empty">
                  No decisions have been scored yet.
                </p>
              ) : (
                <StackedBar
                  label="Decisions by verdict"
                  segments={[
                    { key: "RECOMMEND", label: "Recommend", value: verdicts?.RECOMMEND ?? 0, tone: "ok" },
                    { key: "REVIEW", label: "Review", value: verdicts?.REVIEW ?? 0, tone: "warn" },
                    { key: "REJECT", label: "Reject", value: verdicts?.REJECT ?? 0, tone: "bad" },
                  ]}
                />
              )
            ) : (
              <p className="text-sm text-muted">—</p>
            )}
          </Panel>

          <Panel
            title="Recent decisions"
            padded={false}
            actions={
              <Link to="/runs" className="text-xs text-accent hover:underline">
                All runs
              </Link>
            }
          >
            {runs.isLoading ? (
              <LoadingState label="Loading runs…" />
            ) : runs.isError ? (
              <ErrorState title="Could not load runs" error={runs.error} onRetry={() => void runs.refetch()} />
            ) : !runs.data || runs.data.length === 0 ? (
              <EmptyState
                title="No runs yet"
                hint="Start a run and its decision appears here."
                action={
                  <Link to="/new" className="text-accent hover:underline">
                    New run
                  </Link>
                }
              />
            ) : (
              <RunsTable runs={runs.data} compact />
            )}
          </Panel>
        </div>

        <Panel title="Live events" padded={false} className="self-start">
          <ActivityFeed />
        </Panel>
      </div>
    </div>
  );
}
