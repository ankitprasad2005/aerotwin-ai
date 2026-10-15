import { useDecisionWeights } from "../../api/useDecisionWeights";
import type { Decision, OrchestrationRunStatus } from "../../types";
import { readValidation, VERDICT_HELP } from "../../utils/decision";
import { formatFraction, formatSignedUsd, formatUsdValue } from "../../utils/format";
import { BreakdownBars, type BarItem } from "../charts/BreakdownBars";
import { Gauge } from "../charts/Gauge";
import { RiskBadge, VerdictBadge } from "../ui/Badge";
import { Panel } from "../ui/Panel";
import { Tooltip } from "../ui/Tooltip";

function Money({ label, value, hint, signed = false }: { label: string; value: number; hint: string; signed?: boolean }) {
  const negative = value < 0;
  return (
    <div title={hint} className="rounded-sm border border-line bg-canvas px-2.5 py-1.5">
      <div className="label text-muted">{label}</div>
      <div className={`font-mono text-lg font-semibold ${signed ? (negative ? "text-bad" : "text-ok") : "text-ink-strong"}`}>
        {signed ? formatSignedUsd(value) : formatUsdValue(value)}
      </div>
    </div>
  );
}

function IssueList({ title, items, tone }: { title: string; items: string[]; tone: "bad" | "warn" }) {
  if (items.length === 0) return null;
  const color = tone === "bad" ? "border-bad/40 bg-bad/5 text-bad" : "border-warn/40 bg-warn/5 text-warn";
  return (
    <div className={`rounded-sm border px-2.5 py-2 ${color}`} data-testid={`issues-${tone}`}>
      <div className="label">
        {title} ({items.length})
      </div>
      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm text-ink">
        {items.map((item, index) => (
          <li key={`${index}-${item}`} className="break-words">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function toneFor(value: number): BarItem["tone"] {
  if (value >= 0.7) return "ok";
  if (value >= 0.4) return "accent";
  return "warn";
}

/** The first thing on the run page: the reconciled decision, its verdict and score, how each
 * factor contributed, the money, and everything that blocked or weakened it. */
export function DecisionPanel({
  decision,
  runStatus,
}: {
  decision: Decision | null;
  runStatus: OrchestrationRunStatus;
}) {
  // Thresholds colour the gauge. If the weights can't be loaded the defaults are used, which only
  // affects colour, so a failure here is deliberately silent.
  const { data: weights } = useDecisionWeights();

  if (!decision) {
    const message =
      runStatus === "FAILED"
        ? "This prompt failed before a decision could be made. Check the Events tab for the reason."
        : runStatus === "RUNNING"
          ? "The agents are still working. The decision appears here as soon as they finish."
          : "No decision was recorded for this prompt.";
    return (
      <Panel title="Decision" data-testid="decision-panel">
        <p className="text-sm text-muted" data-testid="decision-empty">
          {message}
        </p>
      </Panel>
    );
  }

  const validation = readValidation(decision.validation_result);
  const items: BarItem[] = validation.breakdown.map((row) => ({
    key: row.key,
    label: row.label,
    fraction: row.value,
    detail: `${row.contribution.toFixed(1)} pts`,
    tone: toneFor(row.value),
    hint: `Factor value ${row.value.toFixed(2)} × weight ${Math.round(row.weight * 100)}%`,
  }));

  return (
    <Panel title="Decision" data-testid="decision-panel">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <VerdictBadge verdict={validation.verdict} withHelp />
            <Tooltip content="Risk level assigned by the decision engine.">
              <span className="flex items-center gap-1.5 text-xs text-muted">
                Risk <RiskBadge risk={validation.risk} />
              </span>
            </Tooltip>
            <span className="flex items-center gap-1.5 text-xs text-muted">
              Constraints
              <span
                className={`font-mono font-semibold ${
                  validation.constraints === "FAIL" ? "text-bad" : validation.constraints === "PASS" ? "text-ok" : "text-muted"
                }`}
              >
                {validation.constraints ?? "—"}
              </span>
            </span>
            <span className="text-xs text-muted">
              Confidence <span className="font-mono text-ink">{formatFraction(decision.confidence)}</span>
            </span>
          </div>
          {validation.verdict === null && (
            <p className="text-xs text-muted">This decision was made before weighted scoring, so it has no verdict or score.</p>
          )}
          <p className="break-words text-base text-ink-strong" data-testid="decision-summary-text">
            {decision.summary}
          </p>
          <div className="grid grid-cols-3 gap-2">
            <Money label="Revenue / wk" value={decision.expected_revenue_impact} hint="Expected weekly revenue change" />
            <Money label="Cost / wk" value={decision.expected_cost_impact} hint="Expected weekly cost change" />
            <Money label="Profit / wk" value={decision.expected_profit_impact} hint="Revenue minus cost" signed />
          </div>
          <IssueList title="Blocking conflicts" items={validation.conflicts} tone="bad" />
          <IssueList title="Warnings" items={validation.warnings} tone="warn" />
          {decision.risks.length > 0 && (
            <details className="rounded-sm border border-line px-2.5 py-1.5">
              <summary className="label cursor-pointer text-muted">Risks ({decision.risks.length})</summary>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm">
                {decision.risks.map((risk, index) => (
                  <li key={`${index}-${risk}`} className="break-words">
                    {risk}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <details className="rounded-sm border border-line px-2.5 py-1.5">
            <summary className="label cursor-pointer text-muted">
              Constraints checked ({decision.constraints_checked.length})
            </summary>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm">
              {decision.constraints_checked.map((constraint, index) => (
                <li key={`${index}-${constraint}`} className="break-words">
                  {constraint}
                </li>
              ))}
            </ul>
          </details>
        </div>

        <div className="min-w-0 space-y-3">
          <div className="flex flex-col items-center">
            <Gauge value={validation.score} thresholds={weights?.thresholds} label="Decision score" />
            {validation.verdict && <p className="mt-1 text-center text-xs text-muted">{VERDICT_HELP[validation.verdict]}</p>}
          </div>
          <div>
            <div className="label mb-1.5 text-muted">Score breakdown</div>
            {items.length > 0 ? (
              <>
                <BreakdownBars items={items} label="Score breakdown" />
                <p className="mt-1.5 text-xs text-faint">Bars show each factor (0-100%). Points are its weighted share of the score.</p>
              </>
            ) : (
              <p className="text-sm text-muted" data-testid="breakdown-missing">
                No factor breakdown. Decisions made before weighted scoring do not have one.
              </p>
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}
