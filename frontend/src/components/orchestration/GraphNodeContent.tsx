import { StatusPill } from "../ui/StatusPill";

export function GraphNodeContent({ label, status }: { label: string; status: string }) {
  return (
    <div className="border border-line-strong bg-panel px-md py-sm" data-testid="graph-node-content">
      <div className="label text-ink">{label}</div>
      <StatusPill status={status} />
    </div>
  );
}
