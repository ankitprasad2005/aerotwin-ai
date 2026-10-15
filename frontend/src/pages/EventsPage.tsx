import { useState } from "react";
import type { EventFilters as EventFiltersType } from "../api/useEvents";
import { EventFilters } from "../components/events/EventFilters";
import { EventTable } from "../components/events/EventTable";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel } from "../components/ui/Panel";

export function EventsPage() {
  const [filters, setFilters] = useState<EventFiltersType>({});

  return (
    <div data-testid="page-content">
      <PageHeader
        title="Events"
        subtitle="Everything the platform records while it works. Click a row that belongs to an agent to inspect it. Turn on Debug in the top bar to see raw payloads."
      />
      <Panel title="Filters" className="mb-3">
        <EventFilters filters={filters} onChange={setFilters} />
      </Panel>
      <Panel padded={false}>
        <EventTable filters={filters} />
      </Panel>
    </div>
  );
}
