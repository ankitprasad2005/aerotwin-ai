import type { EventFilters as EventFiltersType } from "../../api/useEvents";

export function EventFilters({
  filters,
  onChange,
}: {
  filters: EventFiltersType;
  onChange: (filters: EventFiltersType) => void;
}) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1">
        <span className="label text-muted">Severity</span>
        <select
          value={filters.severity ?? ""}
          onChange={(event) => onChange({ ...filters, severity: event.target.value || undefined })}
          className="field font-mono"
        >
          <option value="">ALL</option>
          <option value="INFO">INFO</option>
          <option value="WARN">WARN</option>
          <option value="ERROR">ERROR</option>
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="label text-muted">Event type</span>
        <input
          type="text"
          value={filters.event_type ?? ""}
          onChange={(event) => onChange({ ...filters, event_type: event.target.value || undefined })}
          placeholder="e.g. agent.completed"
          className="field font-mono"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="label text-muted">Run ID</span>
        <input
          type="text"
          value={filters.run_id ?? ""}
          onChange={(event) => onChange({ ...filters, run_id: event.target.value || undefined })}
          className="field font-mono"
        />
      </label>
    </div>
  );
}
