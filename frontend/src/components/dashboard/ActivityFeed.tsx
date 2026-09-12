import { useEventStreamStore } from "../../stores/eventStreamStore";
import { formatEventLine } from "../../utils/formatEvent";

export function ActivityFeed() {
  const events = useEventStreamStore((state) => state.events);

  if (events.length === 0) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[NO EVENTS YET]</div>
    );
  }

  return (
    <ul className="flex max-h-96 flex-col gap-xs overflow-y-auto" data-testid="activity-feed">
      {events.map((event) => {
        const line = formatEventLine(event);
        return (
          <li key={event.id} className="font-mono text-body-sm text-text-primary">
            <span className="text-text-secondary">[{line.timestamp}]</span> <span>{line.source}</span>{" "}
            <span className="text-text-secondary">{line.message}</span>
          </li>
        );
      })}
    </ul>
  );
}
