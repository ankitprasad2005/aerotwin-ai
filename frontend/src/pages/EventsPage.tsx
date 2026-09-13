import { useState } from "react";
import type { EventFilters as EventFiltersType } from "../api/useEvents";
import { EventFilters } from "../components/events/EventFilters";
import { EventTable } from "../components/events/EventTable";

export function EventsPage() {
  const [filters, setFilters] = useState<EventFiltersType>({});

  return (
    <div data-testid="page-content" className="flex flex-col gap-xl">
      <h1 className="font-display text-3xl text-text-display">EVENTS</h1>
      <EventFilters filters={filters} onChange={setFilters} />
      <EventTable filters={filters} />
    </div>
  );
}
