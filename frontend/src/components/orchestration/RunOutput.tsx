import { useRunDetail } from "../../api/useRuns";
import type { Decision } from "../../types";
import { formatUsd } from "../../utils/formatMoney";
import { RecommendationView } from "../inspector/RecommendationView";
import { StatusPill } from "../ui/StatusPill";

const RISK_COLOR: Record<string, string> = { LOW: "text-success", MEDIUM: "text-warning", HIGH: "text-accent" };

function Row({ label, value, className = "" }: { label: string; value: string; className?: string }) {
  return (
    <>
      <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">{label}</dt>
      <dd className={`font-mono text-body-sm text-text-primary ${className}`}>{value}</dd>
    </>
  );
}

function StringList({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="mt-sm">
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
        {label} ({values.length})
      </div>
      <ul className="mt-xs flex flex-col gap-2xs font-mono text-body-sm text-text-primary">
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
}

function DecisionOutput({ decision }: { decision: Decision }) {
  const validation = decision.validation_result as { risk?: unknown; constraints?: unknown; conflicts?: unknown };
  const risk = typeof validation.risk === "string" ? validation.risk : "—";
  const constraints = typeof validation.constraints === "string" ? validation.constraints : "—";
  const conflicts = Array.isArray(validation.conflicts) ? validation.conflicts.map(String) : [];

  return (
    <div className="border border-border p-md" data-testid="final-decision-output">
      <p className="text-body text-text-display">{decision.summary}</p>
      <dl className="mt-sm grid grid-cols-2 gap-sm">
        <Row label="Weekly profit impact" value={formatUsd(decision.expected_profit_impact)} />
        <Row label="Weekly revenue impact" value={formatUsd(decision.expected_revenue_impact)} />
        <Row label="Weekly cost impact" value={formatUsd(decision.expected_cost_impact)} />
        <Row label="Confidence" value={`${Math.round(decision.confidence * 100)}%`} />
        <Row label="Risk" value={risk} className={RISK_COLOR[risk] ?? ""} />
        <Row label="Constraints" value={constraints} className={constraints === "FAIL" ? "text-accent" : ""} />
      </dl>
      {conflicts.length > 0 && <StringList label="Conflicts" values={conflicts} />}
      {decision.risks.length > 0 && <StringList label="Risks" values={decision.risks} />}
      <StringList label="Constraints checked" values={decision.constraints_checked} />
    </div>
  );
}

/** The run's full output on one page: what each agent recommended, and the combined decision the
 * decision engine reconciled from them. The Agent Inspector and Decision Summary slide-overs show
 * the same data per node, but only one node at a time and only via the graph. */
export function RunOutput({ runId }: { runId: string }) {
  const { data: run, isLoading, isError } = useRunDetail(runId);

  if (isLoading) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[LOADING OUTPUT...]</div>
    );
  }
  if (isError || !run) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-accent">[ERROR LOADING OUTPUT]</div>
    );
  }

  return (
    <div className="flex flex-col gap-lg" data-testid="run-output">
      <section>
        <h2 className="mb-md font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Agent outputs</h2>
        {run.agent_executions.length === 0 ? (
          <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
            [NO AGENT OUTPUT YET]
          </div>
        ) : (
          <div className="flex flex-col gap-md">
            {run.agent_executions.map((execution) => (
              <div key={execution.id} className="border border-border p-md" data-testid="agent-output">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-primary">
                    {execution.agent_type} AGENT
                  </span>
                  <StatusPill status={execution.status} />
                </div>
                <div className="mt-sm">
                  <RecommendationView recommendation={execution.recommendation} />
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-md font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Final decision</h2>
        {run.decision ? (
          <DecisionOutput decision={run.decision} />
        ) : (
          <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
            [NO DECISION — RUN {run.status}]
          </div>
        )}
      </section>
    </div>
  );
}
