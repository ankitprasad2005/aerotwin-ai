import { useConnectionStore } from "../../stores/connectionStore";
import { useDebugStore } from "../../stores/debugStore";
import { useEventStreamStore } from "../../stores/eventStreamStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import { formatEventLine } from "../../utils/formatEvent";
import { EmptyState } from "../ui/States";

const SEVERITY_DOT: Record<string, string> = { INFO: "bg-faint", WARN: "bg-warn", ERROR: "bg-bad" };

/** The live event feed, newest first. Rows that belong to an agent open its inspector. */
export function ActivityFeed({ limit = 60 }: { limit?: number }) {
  const events = useEventStreamStore((state) => state.events);
  const status = useConnectionStore((state) => state.status);
  const debugEnabled = useDebugStore((state) => state.enabled);
  const openInspector = useInspectorStore((state) => state.open);

  if (events.length === 0) {
    return (
      <EmptyState
        title={status === "open" ? "Waiting for events" : "Live feed is not connected"}
        hint={
          status === "open"
            ? "Events appear here the moment a run starts. Start one from New run."
            : "The app keeps retrying in the background. Events from before the connection are on the Events page."
        }
      />
    );
  }

  return (
    <ul className="max-h-[420px] divide-y divide-line overflow-y-auto" data-testid="activity-feed">
      {events.slice(0, limit).map((event) => {
        const line = formatEventLine(event);
        const content = (
          <span className="flex items-baseline gap-2">
            <span aria-hidden="true" className={`mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${SEVERITY_DOT[event.severity] ?? "bg-faint"}`} />
            <span className="shrink-0 font-mono text-xs text-muted">{line.timestamp}</span>
            <span className="shrink-0 text-xs font-medium text-ink">{line.source}</span>
            <span className="min-w-0 break-words text-xs text-muted">{line.message}</span>
          </span>
        );
        return (
          <li key={event.id} className="px-3 py-1.5">
            {event.agent_execution_id ? (
              <button
                type="button"
                onClick={() => openInspector(event.agent_execution_id as string)}
                className="block w-full text-left hover:text-ink-strong"
              >
                {content}
              </button>
            ) : (
              content
            )}
            {debugEnabled && (
              <pre className="ml-6 mt-1 overflow-x-auto font-mono text-2xs text-faint">{JSON.stringify(event.payload, null, 2)}</pre>
            )}
          </li>
        );
      })}
    </ul>
  );
}
