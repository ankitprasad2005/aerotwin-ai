import { useState } from "react";
import type { RunIteration, RunDetail } from "../../types";
import { formatDateTime, formatDuration } from "../../utils/format";
import { StatusPill } from "../ui/StatusPill";

const COLLAPSED_CHARS = 220;

/** Run title block: objective (long ones collapse), status, timing, and the iteration switcher. */
export function RunHeader({
  run,
  iterations,
  selected,
  onSelect,
}: {
  run: RunDetail;
  iterations: RunIteration[];
  /** Selected iteration's sequence number. */
  selected: number;
  onSelect: (sequence: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const current = iterations.find((iteration) => iteration.sequence === selected) ?? iterations[iterations.length - 1];
  const objective = current?.objective ?? run.objective;
  const long = objective.length > COLLAPSED_CHARS;
  const shown = long && !expanded ? `${objective.slice(0, COLLAPSED_CHARS).trimEnd()}…` : objective;
  const started = Date.parse(run.created_at);
  const finished = run.completed_at ? Date.parse(run.completed_at) : NaN;
  const duration = Number.isNaN(started) || Number.isNaN(finished) ? null : finished - started;

  return (
    <div className="space-y-2" data-testid="run-header">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="break-words text-lg font-semibold text-ink-strong" data-testid="run-objective">
            {shown}
          </h1>
          {long && (
            <button type="button" className="text-xs text-accent hover:underline" onClick={() => setExpanded((value) => !value)}>
              {expanded ? "Show less" : "Show full objective"}
            </button>
          )}
        </div>
        <StatusPill status={run.status} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        <span>
          Started <span className="text-ink">{formatDateTime(run.created_at)}</span>
        </span>
        <span>
          Duration <span className="font-mono text-ink">{formatDuration(duration)}</span>
        </span>
        <span>
          Run <span className="font-mono text-ink">{run.id}</span>
        </span>
      </div>
      {iterations.length > 1 && (
        <div role="group" aria-label="Prompt" className="flex flex-wrap items-center gap-1">
          <span className="label mr-1 text-muted">Prompt</span>
          {iterations.map((iteration) => {
            const active = iteration.sequence === current?.sequence;
            return (
              <button
                key={iteration.id}
                type="button"
                aria-pressed={active}
                title={iteration.objective}
                onClick={() => onSelect(iteration.sequence)}
                className={`rounded-sm border px-2 py-0.5 text-xs font-medium ${
                  active ? "border-accent bg-accent-subtle text-accent" : "border-line-strong text-muted hover:text-ink"
                }`}
              >
                {iteration.sequence}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
