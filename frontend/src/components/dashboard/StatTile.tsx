import { Label } from "../ui/MonoText";
import { Panel } from "../ui/Panel";

export function StatTile({ label, value }: { label: string; value: number | string }) {
  return (
    <Panel className="p-md" data-testid={`stat-tile-${label}`}>
      <Label>{label}</Label>
      <div className="mt-xs font-display text-4xl text-text-display">{value}</div>
    </Panel>
  );
}
