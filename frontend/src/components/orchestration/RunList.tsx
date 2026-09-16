import { useRuns } from "../../api/useRuns";
import { formatEventTimestamp } from "../../utils/formatEvent";
import { StatusPill } from "../ui/StatusPill";

export function RunList({
  selectedRunId,
  onSelect,
}: {
  selectedRunId: string | null;
  onSelect: (runId: string) => void;
}) {
  const { data: runs, isLoading, isError } = useRuns();

  if (isLoading) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[LOADING RUNS...]</div>
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
    <ul className="flex flex-col" data-testid="run-list">
      {runs.map((run) => {
        const isSelected = run.id === selectedRunId;
        return (
          <li key={run.id}>
            <button
              type="button"
              onClick={() => onSelect(run.id)}
              aria-current={isSelected ? "true" : undefined}
              className={`w-full border-l-2 px-sm py-sm text-left ${
                isSelected ? "border-accent bg-surface" : "border-transparent hover:bg-surface"
              }`}
            >
              <div className="flex items-center justify-between gap-sm">
                <StatusPill status={run.status} />
                <span className="font-mono text-[11px] text-text-disabled">
                  {formatEventTimestamp(run.created_at)}
                </span>
              </div>
              <div className="mt-2xs line-clamp-2 text-body-sm text-text-primary">{run.objective}</div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
