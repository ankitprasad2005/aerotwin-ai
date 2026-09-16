import { useDecisionDetail } from "../../api/useAgentExecutionDetail";
import { formatUsd } from "../../utils/formatMoney";
import { SlideOver } from "../layout/SlideOver";

export function DecisionSummary({ decisionId, onClose }: { decisionId: string | null; onClose: () => void }) {
  const { data: decision, isLoading, isError } = useDecisionDetail(decisionId ?? undefined);

  return (
    <SlideOver open={decisionId !== null} onClose={onClose}>
      <div className="flex flex-col gap-lg p-lg">
        <h2 className="font-display text-2xl text-text-display">DECISION SUMMARY</h2>

        {isLoading && (
          <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[LOADING...]</div>
        )}
        {isError && (
          <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-accent">
            [ERROR LOADING DECISION]
          </div>
        )}

        {decision && (
          <>
            <p className="text-body-sm text-text-primary">{decision.summary}</p>

            <dl className="grid grid-cols-2 gap-sm" data-testid="decision-summary">
              <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
                Confidence
              </dt>
              <dd className="font-mono text-body-sm text-text-primary">
                {Math.round(decision.confidence * 100)}%
              </dd>

              <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
                Weekly profit impact
              </dt>
              <dd className="font-mono text-body-sm text-text-primary">
                {formatUsd(decision.expected_profit_impact)}
              </dd>

              <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
                Weekly revenue impact
              </dt>
              <dd className="font-mono text-body-sm text-text-primary">
                {formatUsd(decision.expected_revenue_impact)}
              </dd>

              <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
                Weekly cost impact
              </dt>
              <dd className="font-mono text-body-sm text-text-primary">
                {formatUsd(decision.expected_cost_impact)}
              </dd>
            </dl>

            {decision.risks.length > 0 && (
              <details className="border border-border p-sm">
                <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
                  Risks ({decision.risks.length})
                </summary>
                <ul className="mt-sm flex flex-col gap-xs font-mono text-body-sm text-text-primary">
                  {decision.risks.map((risk) => (
                    <li key={risk}>{risk}</li>
                  ))}
                </ul>
              </details>
            )}

            <details className="border border-border p-sm">
              <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
                Constraints checked ({decision.constraints_checked.length})
              </summary>
              <ul className="mt-sm flex flex-col gap-xs font-mono text-body-sm text-text-primary">
                {decision.constraints_checked.map((constraint) => (
                  <li key={constraint}>{constraint}</li>
                ))}
              </ul>
            </details>

            <details className="border border-border p-sm">
              <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
                Validation result
              </summary>
              <pre className="mt-sm overflow-x-auto font-mono text-body-sm text-text-primary">
                {JSON.stringify(decision.validation_result, null, 2)}
              </pre>
            </details>
          </>
        )}
      </div>
    </SlideOver>
  );
}
