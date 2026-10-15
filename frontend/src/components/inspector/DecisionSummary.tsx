import { useDecisionDetail } from "../../api/useAgentExecutionDetail";
import { formatUsd } from "../../utils/formatMoney";
import { SlideOver } from "../layout/SlideOver";

export function DecisionSummary({ decisionId, onClose }: { decisionId: string | null; onClose: () => void }) {
  const { data: decision, isLoading, isError } = useDecisionDetail(decisionId ?? undefined);

  return (
    <SlideOver open={decisionId !== null} onClose={onClose}>
      <div className="flex flex-col gap-lg p-lg">
        <h2 className="text-lg font-semibold text-ink-strong">DECISION SUMMARY</h2>

        {isLoading && (
          <div className="label text-faint">[LOADING...]</div>
        )}
        {isError && (
          <div className="label text-bad">
            [ERROR LOADING DECISION]
          </div>
        )}

        {decision && (
          <>
            <p className="text-sm text-ink">{decision.summary}</p>

            <dl className="grid grid-cols-2 gap-sm" data-testid="decision-summary">
              <dt className="label text-muted">
                Confidence
              </dt>
              <dd className="font-mono text-sm text-ink">
                {Math.round(decision.confidence * 100)}%
              </dd>

              <dt className="label text-muted">
                Weekly profit impact
              </dt>
              <dd className="font-mono text-sm text-ink">
                {formatUsd(decision.expected_profit_impact)}
              </dd>

              <dt className="label text-muted">
                Weekly revenue impact
              </dt>
              <dd className="font-mono text-sm text-ink">
                {formatUsd(decision.expected_revenue_impact)}
              </dd>

              <dt className="label text-muted">
                Weekly cost impact
              </dt>
              <dd className="font-mono text-sm text-ink">
                {formatUsd(decision.expected_cost_impact)}
              </dd>
            </dl>

            {decision.risks.length > 0 && (
              <details className="border border-line p-sm">
                <summary className="cursor-pointer label text-muted">
                  Risks ({decision.risks.length})
                </summary>
                <ul className="mt-sm flex flex-col gap-xs font-mono text-sm text-ink">
                  {decision.risks.map((risk) => (
                    <li key={risk}>{risk}</li>
                  ))}
                </ul>
              </details>
            )}

            <details className="border border-line p-sm">
              <summary className="cursor-pointer label text-muted">
                Constraints checked ({decision.constraints_checked.length})
              </summary>
              <ul className="mt-sm flex flex-col gap-xs font-mono text-sm text-ink">
                {decision.constraints_checked.map((constraint) => (
                  <li key={constraint}>{constraint}</li>
                ))}
              </ul>
            </details>

            <details className="border border-line p-sm">
              <summary className="cursor-pointer label text-muted">
                Validation result
              </summary>
              <pre className="mt-sm overflow-x-auto font-mono text-sm text-ink">
                {JSON.stringify(decision.validation_result, null, 2)}
              </pre>
            </details>
          </>
        )}
      </div>
    </SlideOver>
  );
}
