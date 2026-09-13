import { StatusPill } from "../ui/StatusPill";

export function GraphNodeContent({ label, status }: { label: string; status: string }) {
  return (
    <div className="border border-border-visible bg-surface px-md py-sm" data-testid="graph-node-content">
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-primary">{label}</div>
      <StatusPill status={status} />
    </div>
  );
}
