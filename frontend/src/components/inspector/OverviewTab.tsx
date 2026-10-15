import type { AgentExecutionDetail } from "../../types";
import { StatusPill } from "../ui/StatusPill";

export function OverviewTab({ detail }: { detail: AgentExecutionDetail }) {
  return (
    <dl className="grid grid-cols-2 gap-sm" data-testid="overview-tab">
      <dt className="label text-muted">Status</dt>
      <dd>
        <StatusPill status={detail.status} />
      </dd>

      <dt className="label text-muted">Agent type</dt>
      <dd className="text-sm text-ink">{detail.agent_type}</dd>

      <dt className="label text-muted">Task</dt>
      <dd className="text-sm text-ink">{detail.task}</dd>

      <dt className="label text-muted">Elapsed</dt>
      <dd className="font-mono text-sm text-ink">
        {detail.elapsed_ms !== null ? `${(detail.elapsed_ms / 1000).toFixed(1)}s` : "—"}
      </dd>

      <dt className="label text-muted">Tokens</dt>
      <dd className="font-mono text-sm text-ink">{detail.total_tokens ?? "—"}</dd>
    </dl>
  );
}
