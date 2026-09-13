import { useEvents } from "../../api/useEvents";
import { formatEventLine } from "../../utils/formatEvent";

export function TimelineView({ agentExecutionId }: { agentExecutionId: string }) {
  const { data: events, isLoading, isError } = useEvents({ agent_execution_id: agentExecutionId });

  if (isLoading) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[LOADING...]</div>
    );
  }
  if (isError) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-accent">
        [ERROR LOADING TIMELINE]
      </div>
    );
  }
  if (!events || events.length === 0) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
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
          <li key={event.id} className="font-mono text-body-sm text-text-primary">
            <span className="text-text-secondary">[{line.timestamp}]</span> {line.message}
          </li>
        );
      })}
    </ol>
  );
}
