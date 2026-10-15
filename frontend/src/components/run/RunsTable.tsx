import { Link, useNavigate } from "react-router-dom";
import type { StatsRun } from "../../types/api";
import { formatDateTime, formatDuration, formatNumber, formatScore, formatSignedUsd } from "../../utils/format";
import { RiskBadge, VerdictBadge } from "../ui/Badge";
import { StatusPill } from "../ui/StatusPill";

/** A dense table of runs with their decision outcome. Used by the Runs page and the Overview. */
export function RunsTable({ runs, compact = false }: { runs: StatsRun[]; compact?: boolean }) {
  const navigate = useNavigate();
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse" data-testid="runs-table">
        <thead>
          <tr className="border-b border-line">
            <th className="th">Objective</th>
            <th className="th">Status</th>
            <th className="th">Verdict</th>
            <th className="th text-right">Score</th>
            <th className="th text-right">Profit / wk</th>
            {!compact && <th className="th">Risk</th>}
            {!compact && <th className="th text-right">Prompts</th>}
            {!compact && <th className="th text-right">Tokens</th>}
            {!compact && <th className="th text-right">Time</th>}
            <th className="th">Started</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const profit = run.decision?.expected_profit_impact;
            return (
              <tr
                key={run.id}
                onClick={() => navigate(`/runs/${run.id}`)}
                className="cursor-pointer border-b border-line last:border-0 hover:bg-panel-raised"
              >
                <td className="td max-w-[380px]">
                  <Link
                    to={`/runs/${run.id}`}
                    onClick={(event) => event.stopPropagation()}
                    title={run.objective}
                    className="block truncate font-medium text-ink-strong hover:text-accent"
                  >
                    {run.objective}
                  </Link>
                  {run.decision && (
                    <span className="block truncate text-xs text-muted" title={run.decision.summary}>
                      {run.decision.summary}
                    </span>
                  )}
                </td>
                <td className="td">
                  <StatusPill status={run.status} />
                </td>
                <td className="td">
                  <VerdictBadge verdict={run.decision?.verdict} />
                </td>
                <td className="td text-right font-mono">{formatScore(run.decision?.score)}</td>
                <td
                  className={`td text-right font-mono ${
                    typeof profit === "number" ? (profit < 0 ? "text-bad" : "text-ok") : ""
                  }`}
                >
                  {formatSignedUsd(profit)}
                </td>
                {!compact && (
                  <td className="td">
                    <RiskBadge risk={run.decision?.risk} />
                  </td>
                )}
                {!compact && <td className="td text-right font-mono">{run.iterations}</td>}
                {!compact && <td className="td text-right font-mono">{formatNumber(run.total_tokens)}</td>}
                {!compact && <td className="td text-right font-mono">{formatDuration(run.duration_ms)}</td>}
                <td className="td whitespace-nowrap text-muted">{formatDateTime(run.created_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
