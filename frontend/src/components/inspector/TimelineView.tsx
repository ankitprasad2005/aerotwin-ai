import { useEvents } from "../../api/useEvents";
import { formatEventLine } from "../../utils/formatEvent";

export function TimelineView({ agentExecutionId }: { agentExecutionId: string }) {
  const { data: events, isLoading, isError } = useEvents({ agent_execution_id: agentExecutionId });

  if (isLoading) {
    return (
      <div className="label text-faint">[LOADING...]</div>
    );
  }
  if (isError) {
    return (
      <div className="label text-bad">
        [ERROR LOADING TIMELINE]
      </div>
    );
  }
  if (!events || events.length === 0) {
    return (
      <div className="label text-faint">
        [NO TIMELINE EVENTS]
      </div>
    );
  }

  const chronological = [...events].reverse();

  return (
    <ol className="flex flex-col gap-xs" data-testid="timeline-view">
      {chronological.map((event) => {
        const line = formatEventLine(event);
        return (
          <li key={event.id} className="font-mono text-sm text-ink">
            <span className="text-muted">[{line.timestamp}]</span> {line.message}
          </li>
        );
      })}
    </ol>
  );
}
