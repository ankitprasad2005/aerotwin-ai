import type { EventFilters as EventFiltersType } from "../../api/useEvents";
import { useEvents } from "../../api/useEvents";
import { formatEventTimestamp } from "../../utils/formatEvent";
import { StatusPill } from "../ui/StatusPill";

export function EventTable({ filters }: { filters: EventFiltersType }) {
  const { data: events, isLoading, isError } = useEvents(filters);

  if (isLoading) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[LOADING...]</div>
    );
  }
  if (isError) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-accent">[ERROR LOADING EVENTS]</div>
    );
  }
  if (!events || events.length === 0) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[NO EVENTS MATCH]</div>
    );
  }

  return (
    <table className="w-full border-collapse font-mono text-body-sm" data-testid="event-table">
      <thead>
        <tr className="border-b border-border-visible text-left text-text-secondary">
          <th className="py-sm pr-md">TIME</th>
          <th className="py-sm pr-md">TYPE</th>
          <th className="py-sm pr-md">SEVERITY</th>
          <th className="py-sm pr-md">RUN</th>
        </tr>
      </thead>
      <tbody>
        {events.map((event) => (
          <tr key={event.id} className="border-b border-border">
            <td className="py-sm pr-md text-text-secondary">{formatEventTimestamp(event.created_at)}</td>
            <td className="py-sm pr-md text-text-primary">{event.event_type}</td>
            <td className="py-sm pr-md">
              <StatusPill status={event.severity} />
            </td>
            <td className="py-sm pr-md text-text-secondary">{event.run_id ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
