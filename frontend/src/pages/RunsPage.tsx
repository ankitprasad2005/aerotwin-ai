import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useStatsRuns } from "../api/useStats";
import { RunsTable } from "../components/run/RunsTable";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel } from "../components/ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { EMPTY_FILTERS, filterRuns, hasActiveFilters, type RunFilters } from "../utils/runs";

export function RunsPage() {
  const { data: runs, isLoading, isError, error, refetch } = useStatsRuns(100);
  const [filters, setFilters] = useState<RunFilters>(EMPTY_FILTERS);
  const filtered = useMemo(() => filterRuns(runs ?? [], filters), [runs, filters]);

  let body;
  if (isLoading) body = <LoadingState label="Loading runs…" />;
  else if (isError) body = <ErrorState title="Could not load runs" error={error} onRetry={() => void refetch()} />;
  else if (!runs || runs.length === 0) {
    body = (
      <EmptyState
        title="No runs yet"
        hint="A run sends your objective to the five agents and ends in a scored decision."
        action={
          <Link to="/new" className="text-accent hover:underline">
            Start your first run
          </Link>
        }
      />
    );
  } else if (filtered.length === 0) {
    body = (
      <EmptyState
        title="No runs match these filters"
        action={
          <Button variant="ghost" onClick={() => setFilters(EMPTY_FILTERS)}>
            Clear filters
          </Button>
        }
      />
    );
  } else body = <RunsTable runs={filtered} />;

  return (
    <div data-testid="page-content">
      <PageHeader
        title="Runs"
        subtitle="Every orchestration run with its decision. Click a row to open the run."
        actions={
          <Link to="/new" className="rounded-sm bg-accent px-3 py-1.5 text-sm font-medium text-canvas hover:bg-accent/90">
            New run
          </Link>
        }
      />
      <Panel className="mb-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="label text-muted">Search</span>
            <input
              type="search"
              value={filters.query}
              onChange={(event) => setFilters({ ...filters, query: event.target.value })}
              placeholder="Objective or decision text"
              className="field w-64"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="label text-muted">Status</span>
            <select
              value={filters.status}
              onChange={(event) => setFilters({ ...filters, status: event.target.value })}
              className="field"
            >
              <option value="">All</option>
              <option value="RUNNING">Running</option>
              <option value="COMPLETED">Completed</option>
              <option value="FAILED">Failed</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="label text-muted">Verdict</span>
            <select
              value={filters.verdict}
              onChange={(event) => setFilters({ ...filters, verdict: event.target.value })}
              className="field"
            >
              <option value="">All</option>
              <option value="RECOMMEND">Recommend</option>
              <option value="REVIEW">Review</option>
              <option value="REJECT">Reject</option>
              <option value="NONE">No verdict</option>
            </select>
          </label>
          {hasActiveFilters(filters) && (
            <Button variant="ghost" onClick={() => setFilters(EMPTY_FILTERS)}>
              Clear
            </Button>
          )}
          {runs && (
            <span className="ml-auto text-xs text-muted" aria-live="polite">
              Showing {filtered.length} of {runs.length}
            </span>
          )}
        </div>
      </Panel>
      <Panel padded={false}>{body}</Panel>
    </div>
  );
}
