import { useRunDetail } from "../../api/useRuns";
import type { AgentExecution, Decision, RunIteration } from "../../types";
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

function AgentOutput({ execution }: { execution: AgentExecution }) {
  return (
    <div className="border border-border p-md" data-testid="agent-output">
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
  );
}

function IterationOutput({ iteration }: { iteration: RunIteration }) {
  return (
    <section className="flex flex-col gap-sm" data-testid="run-iteration">
      <div className="flex items-start justify-between gap-sm border-b border-border pb-xs">
        <div>
          <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
            Prompt {iteration.sequence}
          </span>
          <p className="text-body-sm text-text-primary">{iteration.objective}</p>
        </div>
        <StatusPill status={iteration.status} />
      </div>

      {iteration.agent_executions.length === 0 ? (
        <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
          [NO AGENT OUTPUT YET]
        </div>
      ) : (
        iteration.agent_executions.map((execution) => <AgentOutput key={execution.id} execution={execution} />)
      )}

      {iteration.decision ? (
        <DecisionOutput decision={iteration.decision} />
      ) : (
        <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
          [NO DECISION — {iteration.status}]
        </div>
      )}
    </section>
  );
}

/** A run's full output, one section per prompt: what each agent recommended and the decision
 * reconciled from them. The Agent Inspector and Decision Summary slide-overs show the same data
 * per node, but only one node at a time and only via a graph. */
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

  // Rows created outside the orchestrator have no iteration; render them as a single section so
  // there's one code path.
  const sections: RunIteration[] =
    run.iterations.length > 0
      ? run.iterations
      : [
          {
            id: run.id,
            run_id: run.id,
            sequence: 1,
            objective: run.objective,
            status: run.status,
            created_at: run.created_at,
            completed_at: run.completed_at,
            agent_executions: run.agent_executions,
            decision: run.decision,
          },
        ];

  return (
    <div className="flex flex-col gap-lg" data-testid="run-output">
      {sections.map((iteration) => (
        <IterationOutput key={iteration.id} iteration={iteration} />
      ))}
    </div>
  );
}
