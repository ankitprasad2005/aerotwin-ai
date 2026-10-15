import type { EventFilters as EventFiltersType } from "../../api/useEvents";
import { useEvents } from "../../api/useEvents";
import { useDebugStore } from "../../stores/debugStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import { formatEventTimestamp } from "../../utils/formatEvent";
import { EmptyState, ErrorState, LoadingState } from "../ui/States";
import { StatusPill } from "../ui/StatusPill";

// Matches what the backend's uuid.UUID query param accepts in practice (hyphens optional).
const UUID_PATTERN = /^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$/i;

export function EventTable({ filters }: { filters: EventFiltersType }) {
  // The backend rejects a run_id that isn't a full UUID (422), so while one is still being
  // typed, hold off querying instead of flashing an error state on every keystroke.
  const runIdIncomplete = filters.run_id !== undefined && !UUID_PATTERN.test(filters.run_id);
  const { data: events, isLoading, isError, error, refetch } = useEvents(filters, { enabled: !runIdIncomplete });
  const debugEnabled = useDebugStore((state) => state.enabled);
  const openInspector = useInspectorStore((state) => state.open);

  if (runIdIncomplete) {
    return <EmptyState title="Enter a full run ID" hint="Run IDs are UUIDs; events load once the whole ID is typed." />;
  }
  if (isLoading) return <LoadingState label="Loading events…" />;
  if (isError) return <ErrorState title="Could not load events" error={error} onRetry={() => void refetch()} />;
  if (!events || events.length === 0) {
    return <EmptyState title="No events match" hint="Try clearing a filter. Events also stream in live while runs execute." />;
  }

  return (
    <div className="overflow-x-auto">
    <table className="w-full border-collapse" data-testid="event-table">
      <thead>
        <tr className="border-b border-line">
          <th className="th">TIME</th>
          <th className="th">TYPE</th>
          <th className="th">SEVERITY</th>
          <th className="th">RUN</th>
          {debugEnabled && <th className="th">PAYLOAD</th>}
        </tr>
      </thead>
      <tbody>
        {events.map((event) => {
          const agentExecutionId = event.agent_execution_id;
          const interactiveProps = agentExecutionId
            ? {
                role: "button" as const,
                tabIndex: 0,
                onClick: () => openInspector(agentExecutionId),
                onKeyDown: (keyEvent: React.KeyboardEvent) => {
                  if (keyEvent.key === "Enter" || keyEvent.key === " ") {
                    keyEvent.preventDefault();
                    openInspector(agentExecutionId);
                  }
                },
              }
            : {};

          return (
            <tr
              key={event.id}
              className={`border-b border-line last:border-0 ${
                agentExecutionId ? "cursor-pointer hover:bg-panel-raised" : ""
              }`}
              {...interactiveProps}
            >
              <td className="td whitespace-nowrap font-mono text-muted">{formatEventTimestamp(event.created_at)}</td>
              <td className="td font-mono text-ink">{event.event_type}</td>
              <td className="td">
                <StatusPill status={event.severity} />
              </td>
              <td className="td max-w-[220px] truncate font-mono text-muted" title={event.run_id ?? undefined}>
                {event.run_id ?? "—"}
              </td>
              {debugEnabled && (
                <td className="td">
                  <pre className="max-w-xs overflow-x-auto text-xs text-faint">
                    {JSON.stringify(event.payload)}
                  </pre>
                </td>
              )}
            </tr>
          );
        })}
      </tbody>
    </table>
    </div>
  );
}
