import { useNavigate } from "react-router-dom";
import { useRuns } from "../../api/useRuns";
import { StatusPill } from "../ui/StatusPill";

export function RecentRunsList() {
  const { data: runs, isLoading, isError } = useRuns();
  const navigate = useNavigate();

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
        <li key={run.id} className="border-b border-border">
          <button
            type="button"
            onClick={() => navigate(`/orchestration?run=${run.id}`)}
            className="flex w-full items-center justify-between py-sm text-left hover:text-text-display"
          >
            <span className="text-body-sm text-text-primary">{run.objective}</span>
            <StatusPill status={run.status} />
          </button>
        </li>
      ))}
    </ul>
  );
}
