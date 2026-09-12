import { useRuns } from "../../api/useRuns";
import { StatusPill } from "../ui/StatusPill";

export function RecentRunsList() {
  const { data: runs, isLoading, isError } = useRuns();

  if (isLoading) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[LOADING...]</div>
    );
  }
  if (isError) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-accent">[ERROR LOADING RUNS]</div>
    );
  }
  if (!runs || runs.length === 0) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[NO RUNS YET]</div>
    );
  }

  return (
    <ul className="flex flex-col gap-sm" data-testid="recent-runs-list">
      {runs.map((run) => (
        <li key={run.id} className="flex items-center justify-between border-b border-border py-sm">
          <span className="text-body-sm text-text-primary">{run.objective}</span>
          <StatusPill status={run.status} />
        </li>
      ))}
    </ul>
  );
}
