import type { AgentExecutionDetail } from "../../types";
import { StatusPill } from "../ui/StatusPill";

export function OverviewTab({ detail }: { detail: AgentExecutionDetail }) {
  return (
    <dl className="grid grid-cols-2 gap-sm" data-testid="overview-tab">
      <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Status</dt>
      <dd>
        <StatusPill status={detail.status} />
      </dd>

      <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Agent type</dt>
      <dd className="text-body-sm text-text-primary">{detail.agent_type}</dd>

      <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Task</dt>
      <dd className="text-body-sm text-text-primary">{detail.task}</dd>

      <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Elapsed</dt>
      <dd className="font-mono text-body-sm text-text-primary">
        {detail.elapsed_ms !== null ? `${(detail.elapsed_ms / 1000).toFixed(1)}s` : "—"}
      </dd>

      <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Tokens</dt>
      <dd className="font-mono text-body-sm text-text-primary">{detail.total_tokens ?? "—"}</dd>
    </dl>
  );
}
