import { useDebugStore } from "../../stores/debugStore";
import { useEventStreamStore } from "../../stores/eventStreamStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import { formatEventLine } from "../../utils/formatEvent";

export function ActivityFeed() {
  const events = useEventStreamStore((state) => state.events);
  const debugEnabled = useDebugStore((state) => state.enabled);
  const openInspector = useInspectorStore((state) => state.open);

  if (events.length === 0) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[NO EVENTS YET]</div>
    );
  }

  return (
    <ul className="flex max-h-96 flex-col gap-xs overflow-y-auto" data-testid="activity-feed">
      {events.map((event) => {
        const line = formatEventLine(event);
        const content = (
          <>
            <span className="text-text-secondary">[{line.timestamp}]</span> <span>{line.source}</span>{" "}
            <span className="text-text-secondary">{line.message}</span>
          </>
        );
        return (
          <li key={event.id} className="font-mono text-body-sm text-text-primary">
            {event.agent_execution_id ? (
              <button
                type="button"
                onClick={() => openInspector(event.agent_execution_id as string)}
                className="text-left hover:text-text-display"
              >
                {content}
              </button>
            ) : (
              content
            )}
            {debugEnabled && (
              <pre className="ml-lg mt-2xs overflow-x-auto font-mono text-[11px] text-text-disabled">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            )}
          </li>
        );
      })}
    </ul>
  );
}
