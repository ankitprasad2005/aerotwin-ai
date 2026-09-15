import { useRuns } from "../api/useRuns";
import { ActivityFeed } from "../components/dashboard/ActivityFeed";
import { RecentRunsList } from "../components/dashboard/RecentRunsList";
import { StatTile } from "../components/dashboard/StatTile";
import { useEventStreamStore } from "../stores/eventStreamStore";

const LIVE_AGENT_STATUSES = new Set(["RUNNING", "WAITING_FOR_LLM", "WAITING_FOR_TOOL"]);

export function DashboardPage() {
  const runStatuses = useEventStreamStore((state) => state.runStatuses);
  const agentExecutionStatuses = useEventStreamStore((state) => state.agentExecutionStatuses);
  const { data: runs } = useRuns();

  // Merge two sources: the live event-stream store only knows about runs that emitted an
  // event since this tab was opened, so a run already RUNNING before that (per the fetched
  // list) would otherwise be missed entirely. A terminal status in the fetched list is final,
  // though, so it wins over a stale live RUNNING (e.g. the completion event was missed while
  // the WebSocket was reconnecting) — otherwise that run would count as active forever.
  const runStatusById = new Map(Object.entries(runStatuses));
  for (const run of runs ?? []) {
    if (run.status !== "RUNNING" || !runStatusById.has(run.id)) {
      runStatusById.set(run.id, run.status);
    }
  }
  const activeRuns = [...runStatusById.values()].filter((status) => status === "RUNNING").length;
  const agentsRunningNow = Object.values(agentExecutionStatuses).filter((status) =>
    LIVE_AGENT_STATUSES.has(status),
  ).length;
  const failedRuns = (runs ?? []).filter((run) => run.status === "FAILED").length;
  const today = new Date().toDateString();
  const decisionsToday = (runs ?? []).filter(
    (run) => run.status === "COMPLETED" && run.completed_at && new Date(run.completed_at).toDateString() === today,
  ).length;

  return (
    <div data-testid="page-content" className="flex flex-col gap-xl">
      <h1 className="font-display text-3xl text-text-display">DASHBOARD</h1>
      <div className="grid grid-cols-4 gap-md">
        <StatTile label="ACTIVE RUNS" value={activeRuns} />
        <StatTile label="AGENTS RUNNING NOW" value={agentsRunningNow} />
        <StatTile label="DECISIONS TODAY" value={decisionsToday} />
        <StatTile label="FAILED" value={failedRuns} />
      </div>
      <div className="grid grid-cols-2 gap-xl">
        <div>
          <h2 className="mb-md font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Activity</h2>
          <ActivityFeed />
        </div>
        <div>
          <h2 className="mb-md font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
            Recent Runs
          </h2>
          <RecentRunsList />
        </div>
      </div>
    </div>
  );
}
