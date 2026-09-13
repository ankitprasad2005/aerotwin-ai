import type { EventFilters as EventFiltersType } from "../../api/useEvents";

export function EventFilters({
  filters,
  onChange,
}: {
  filters: EventFiltersType;
  onChange: (filters: EventFiltersType) => void;
}) {
  return (
    <div className="flex flex-wrap items-end gap-md">
      <label className="flex flex-col gap-xs">
        <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Severity</span>
        <select
          value={filters.severity ?? ""}
          onChange={(event) => onChange({ ...filters, severity: event.target.value || undefined })}
          className="border border-border-visible bg-black p-sm font-mono text-body-sm text-text-primary"
        >
          <option value="">ALL</option>
          <option value="INFO">INFO</option>
          <option value="WARN">WARN</option>
          <option value="ERROR">ERROR</option>
        </select>
      </label>
      <label className="flex flex-col gap-xs">
        <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Event type</span>
        <input
          type="text"
          value={filters.event_type ?? ""}
          onChange={(event) => onChange({ ...filters, event_type: event.target.value || undefined })}
          placeholder="e.g. agent.completed"
          className="border border-border-visible bg-black p-sm font-mono text-body-sm text-text-primary"
        />
      </label>
      <label className="flex flex-col gap-xs">
        <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Run ID</span>
        <input
          type="text"
          value={filters.run_id ?? ""}
          onChange={(event) => onChange({ ...filters, run_id: event.target.value || undefined })}
          className="border border-border-visible bg-black p-sm font-mono text-body-sm text-text-primary"
        />
      </label>
    </div>
  );
}
