import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useRunDetail, useRunEvidence } from "../api/useRuns";
import { EventTable } from "../components/events/EventTable";
import { ExecutionGraph } from "../components/orchestration/ExecutionGraph";
import { KnowledgeGraph } from "../components/orchestration/KnowledgeGraph";
import { PromptPanel } from "../components/orchestration/PromptPanel";
import { AgentsTable } from "../components/run/AgentsTable";
import { DecisionPanel } from "../components/run/DecisionPanel";
import { EvidenceTab } from "../components/run/EvidenceTab";
import { MessagesTab } from "../components/run/MessagesTab";
import { RunHeader } from "../components/run/RunHeader";
import { Panel } from "../components/ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { TabPanel, Tabs, type TabDef } from "../components/ui/Tabs";
import type { RunDetail, RunIteration } from "../types";

type TabKey = "execution" | "knowledge" | "evidence" | "messages" | "events";

/** Rows created outside the orchestrator have no iterations; present them as a single prompt so
 * the rest of the page has one code path. */
function iterationsOf(run: RunDetail): RunIteration[] {
  if (run.iterations.length > 0) return run.iterations;
  return [
    {
      id: run.id,
      run_id: run.id,
      sequence: 1,
      objective: run.objective,
      status: run.status,
      created_at: run.created_at,
      completed_at: run.completed_at,
      agent_executions: run.agent_executions,
      decision: run.decision,
    },
  ];
}

export function RunPage() {
  const { id } = useParams<{ id: string }>();
  const { data: run, isLoading, isError, error, refetch } = useRunDetail(id);
  const { data: evidence } = useRunEvidence(id);
  // null follows the newest prompt, so a follow-up that finishes while the page is open appears
  // without a click; picking an older prompt pins it.
  const [pinned, setPinned] = useState<number | null>(null);
  const [tab, setTab] = useState<TabKey>("execution");

  const iterations = useMemo(() => (run ? iterationsOf(run) : []), [run]);
  const latest = iterations[iterations.length - 1];
  const current = iterations.find((iteration) => iteration.sequence === pinned) ?? latest;

  const titles = useMemo(() => {
    const map: Record<string, string> = {};
    for (const entry of evidence ?? []) for (const item of entry.evidence) map[item.id] = item.title;
    return map;
  }, [evidence]);
  const evidenceCount = useMemo(
    () => new Set((evidence ?? []).filter((entry) => entry.iteration === current?.sequence).flatMap((entry) => entry.evidence.map((item) => item.id))).size,
    [evidence, current?.sequence],
  );

  if (isLoading) {
    return (
      <div data-testid="page-content">
        <LoadingState label="Loading run…" />
      </div>
    );
  }
  if (isError || !run) {
    const missing = error instanceof ApiError && error.status === 404;
    return (
      <div data-testid="page-content" className="max-w-xl space-y-3">
        {missing ? (
          <EmptyState
            title="Run not found"
            hint="It may have been deleted, or the link is wrong."
            action={
              <Link to="/runs" className="text-accent hover:underline">
                Back to all runs
              </Link>
            }
          />
        ) : (
          <ErrorState title="Could not load this run" error={error} onRetry={() => void refetch()} />
        )}
      </div>
    );
  }

  const tabs: TabDef<TabKey>[] = [
    { key: "execution", label: "Execution graph" },
    { key: "knowledge", label: "Knowledge graph" },
    { key: "evidence", label: "Evidence", badge: evidence ? evidenceCount : undefined },
    { key: "messages", label: "Messages" },
    { key: "events", label: "Events" },
  ];

  return (
    <div data-testid="page-content" className="flex flex-col gap-3">
      <RunHeader
        run={run}
        iterations={iterations}
        selected={current.sequence}
        onSelect={(sequence) => setPinned(sequence === latest.sequence ? null : sequence)}
      />
      <DecisionPanel decision={current.decision} runStatus={current.status} />
      <AgentsTable executions={current.agent_executions} titles={titles} />

      <Panel padded={false} data-testid="run-tabs">
        <div className="px-2">
          <Tabs label="Run details" tabs={tabs} active={tab} onChange={setTab} />
        </div>
        <div className="p-3">
          <TabPanel id={tab}>
            {tab === "execution" && <ExecutionGraph runId={run.id} />}
            {tab === "knowledge" && <KnowledgeGraph runId={run.id} />}
            {tab === "evidence" && <EvidenceTab runId={run.id} iteration={current.sequence} />}
            {tab === "messages" && <MessagesTab runId={run.id} />}
            {tab === "events" && <EventTable filters={{ run_id: run.id, limit: 200 }} />}
          </TabPanel>
        </div>
      </Panel>

      <Panel title="Ask a follow-up">
        <PromptPanel runId={run.id} />
      </Panel>
    </div>
  );
}
