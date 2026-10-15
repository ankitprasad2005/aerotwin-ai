import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateRun } from "../api/useRuns";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel } from "../components/ui/Panel";
import { useEventStreamStore } from "../stores/eventStreamStore";

export const MAX_OBJECTIVE_LENGTH = 2000;

export const OBJECTIVE_TEMPLATES = [
  "Improve airline profitability while maintaining passenger capacity",
  "Protect load factor on the thin routes",
  "Reduce exposure to rising jet fuel prices",
  "Grow cargo revenue on the busiest routes",
  "Add capacity where demand is highest without breaching crew limits",
];

export function NewRunPage() {
  const [objective, setObjective] = useState("");
  const navigate = useNavigate();
  const createRun = useCreateRun();
  const events = useEventStreamStore((state) => state.events);
  // POST /api/runs only answers once the whole pipeline has finished, but the run exists (and
  // announces itself on the WebSocket) as soon as it starts. Navigate on that announcement so the
  // run page can update live; the POST response is the fallback when the socket is down.
  const submitted = useRef<{ objective: string; knownEventIds: Set<string> } | null>(null);
  const navigated = useRef(false);

  const trimmed = objective.trim();

  function goTo(runId: string) {
    if (navigated.current) return;
    navigated.current = true;
    navigate(`/runs/${runId}`);
  }

  useEffect(() => {
    const pending = submitted.current;
    if (!pending || navigated.current) return;
    const started = events.find(
      (event) =>
        event.event_type === "orchestration.started" &&
        event.run_id &&
        !pending.knownEventIds.has(event.id) &&
        event.payload.objective === pending.objective,
    );
    if (started?.run_id) goTo(started.run_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!trimmed || createRun.isPending) return;
    navigated.current = false;
    submitted.current = { objective: trimmed, knownEventIds: new Set(events.map((e) => e.id)) };
    createRun.mutate(trimmed, { onSuccess: (run) => goTo(run.id) });
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) submit();
  }

  const remaining = MAX_OBJECTIVE_LENGTH - objective.length;

  return (
    <div data-testid="page-content" className="max-w-3xl">
      <PageHeader
        title="New run"
        subtitle="Describe what you want the airline to optimise. The five agents (network, maintenance, fleet, crew and cargo) analyse it and the decision engine scores the result."
      />
      <Panel>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label htmlFor="objective" className="label text-muted">
            Objective
          </label>
          <textarea
            id="objective"
            value={objective}
            onChange={(event) => setObjective(event.target.value.slice(0, MAX_OBJECTIVE_LENGTH))}
            onKeyDown={onKeyDown}
            rows={5}
            maxLength={MAX_OBJECTIVE_LENGTH}
            disabled={createRun.isPending}
            placeholder="Improve airline profitability while maintaining passenger capacity"
            className="field resize-y text-base"
            aria-describedby="objective-help"
          />
          <div id="objective-help" className="flex justify-between gap-2 text-xs text-muted">
            <span>Ctrl+Enter to run.</span>
            <span className={remaining <= 100 ? "text-warn" : ""} data-testid="objective-counter">
              {objective.length} / {MAX_OBJECTIVE_LENGTH}
            </span>
          </div>

          <div>
            <div className="label mb-1.5 text-muted">Templates</div>
            <div className="flex flex-wrap gap-1.5">
              {OBJECTIVE_TEMPLATES.map((template) => (
                <button
                  key={template}
                  type="button"
                  disabled={createRun.isPending}
                  onClick={() => setObjective(template)}
                  className="rounded-sm border border-line-strong px-2 py-1 text-left text-xs text-ink hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:text-faint"
                >
                  {template}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Button type="submit" disabled={!trimmed || createRun.isPending}>
              {createRun.isPending ? "Starting…" : "Run orchestration"}
            </Button>
            {createRun.isPending && (
              <span role="status" className="text-xs text-muted">
                The agents are working. You will be taken to the run as soon as it starts.
              </span>
            )}
          </div>
          {createRun.isError && (
            <div role="alert" className="rounded-sm border border-bad/40 bg-bad/5 px-3 py-2 text-sm text-bad">
              Could not start the run: {createRun.error?.message ?? "request failed"}
            </div>
          )}
        </form>
      </Panel>
    </div>
  );
}
