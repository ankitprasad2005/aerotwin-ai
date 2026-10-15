import type { KeyboardEvent } from "react";
import type { AgentExecution } from "../../types";
import { formatDuration, formatFraction, formatNumber } from "../../utils/format";
import { agentLabel, summarizeRecommendation } from "../../utils/recommendation";
import { useEventStreamStore } from "../../stores/eventStreamStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import { Chip } from "../ui/Badge";
import { EmptyState } from "../ui/States";
import { Panel } from "../ui/Panel";
import { StatusPill } from "../ui/StatusPill";

const TERMINAL = new Set(["COMPLETED", "FAILED"]);
const MAX_CHIPS = 3;

/** One row per agent. Clicking a row (or pressing Enter/Space on it) opens the agent inspector.
 * Live statuses from the event stream fill in progress for agents that have not finished yet. */
export function AgentsTable({
  executions,
  titles = {},
}: {
  executions: AgentExecution[];
  /** Evidence id -> title, so cited-source chips can say what they point at. */
  titles?: Record<string, string>;
}) {
  const open = useInspectorStore((state) => state.open);
  const liveStatuses = useEventStreamStore((state) => state.agentExecutionStatuses);

  if (executions.length === 0) {
    return (
      <Panel title="Agents" data-testid="agents-table">
        <EmptyState title="No agents have started yet" hint="Agent rows appear here as soon as the pipeline starts." />
      </Panel>
    );
  }

  function onKeyDown(event: KeyboardEvent, id: string) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      open(id);
    }
  }

  return (
    <Panel title="Agents" padded={false} data-testid="agents-table">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-line">
              <th className="th">Agent</th>
              <th className="th">Status</th>
              <th className="th text-right">Time</th>
              <th className="th text-right">Tokens</th>
              <th className="th text-right">Confidence</th>
              <th className="th">Recommendation</th>
              <th className="th">Cited sources</th>
            </tr>
          </thead>
          <tbody>
            {executions.map((execution) => {
              const summary = summarizeRecommendation(execution.recommendation);
              const status = TERMINAL.has(execution.status) ? execution.status : (liveStatuses[execution.id] ?? execution.status);
              const lowConfidence = summary.confidence !== null && summary.confidence < 0.6;
              return (
                <tr
                  key={execution.id}
                  tabIndex={0}
                  aria-label={`Open ${agentLabel(execution.agent_type)} agent`}
                  onClick={() => open(execution.id)}
                  onKeyDown={(event) => onKeyDown(event, execution.id)}
                  className="cursor-pointer border-b border-line last:border-0 hover:bg-panel-raised"
                >
                  <td className="td font-medium text-ink-strong">{agentLabel(execution.agent_type)}</td>
                  <td className="td">
                    <StatusPill status={status} />
                  </td>
                  <td className="td text-right font-mono">{formatDuration(execution.elapsed_ms)}</td>
                  <td className="td text-right font-mono">{formatNumber(execution.total_tokens)}</td>
                  <td className={`td text-right font-mono ${lowConfidence ? "text-warn" : ""}`}>
                    {formatFraction(summary.confidence)}
                  </td>
                  <td className="td max-w-[320px] truncate" title={summary.headline}>
                    {summary.headline}
                  </td>
                  <td className="td">
                    {summary.citedSources.length === 0 ? (
                      <span className="text-muted">none</span>
                    ) : (
                      <span className="flex flex-wrap items-center gap-1">
                        {summary.citedSources.slice(0, MAX_CHIPS).map((id) => (
                          <Chip key={id} title={titles[id] ? `${titles[id]} (${id})` : id}>
                            {id}
                          </Chip>
                        ))}
                        {summary.citedSources.length > MAX_CHIPS && (
                          <span className="text-2xs text-muted" title={summary.citedSources.slice(MAX_CHIPS).join(", ")}>
                            +{summary.citedSources.length - MAX_CHIPS}
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
