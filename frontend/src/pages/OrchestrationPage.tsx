import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useRuns } from "../api/useRuns";
import { ExecutionGraph } from "../components/orchestration/ExecutionGraph";
import { ObjectiveForm } from "../components/orchestration/ObjectiveForm";

export function OrchestrationPage() {
  const [searchParams] = useSearchParams();
  // Deep-link support for RecentRunsList's row click (/orchestration?run=<id>) — read
  // once on mount; the picker itself doesn't write back to the URL as the user changes
  // it, since nothing else needs to observe or share that selection via the URL.
  const [selectedRunId, setSelectedRunId] = useState<string | null>(() => searchParams.get("run"));
  const { data: runs } = useRuns();

  return (
    <div data-testid="page-content" className="flex flex-col gap-xl">
      <h1 className="font-display text-3xl text-text-display">ORCHESTRATION</h1>
      <ObjectiveForm onRunCreated={setSelectedRunId} />

      <div className="flex items-center gap-sm">
        <label
          htmlFor="run-picker"
          className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary"
        >
          View run
        </label>
        <select
          id="run-picker"
          value={selectedRunId ?? ""}
          onChange={(event) => setSelectedRunId(event.target.value || null)}
          className="border border-border-visible bg-black p-sm font-mono text-body-sm text-text-primary"
        >
          <option value="">Select a run…</option>
          {(runs ?? []).map((run) => (
            <option key={run.id} value={run.id}>
              {run.objective} ({run.status})
            </option>
          ))}
        </select>
      </div>

      {selectedRunId ? (
        <ExecutionGraph runId={selectedRunId} />
      ) : (
        <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
          [SELECT OR START A RUN TO VIEW ITS EXECUTION GRAPH]
        </div>
      )}
    </div>
  );
}
