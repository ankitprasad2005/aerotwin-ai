import { Fragment } from "react";
import { formatUsd } from "../../utils/formatMoney";

function humanize(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatValue(key: string, value: string | number | boolean): string {
  if (key === "confidence" && typeof value === "number") return `${Math.round(value * 100)}%`;
  // Every money field the agents emit is named *_impact or *_usd (see app/agents/schemas.py).
  if (typeof value === "number" && (key.endsWith("_impact") || key.endsWith("_usd"))) return formatUsd(value);
  return String(value);
}

/** Renders an agent's structured recommendation: scalars as a field list, arrays as lists, the
 * free-text reasoning last. Field-driven rather than hardcoded, so the network and fleet schemas
 * (and any later agent) all render without a per-agent branch. */
export function RecommendationView({ recommendation }: { recommendation: Record<string, unknown> | null }) {
  if (!recommendation) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
        [NO RECOMMENDATION YET]
      </div>
    );
  }

  const entries = Object.entries(recommendation);
  const scalars = entries.filter(
    ([key, value]) =>
      key !== "reasoning" && (typeof value === "string" || typeof value === "number" || typeof value === "boolean"),
  ) as [string, string | number | boolean][];
  const lists = entries.filter(([, value]) => Array.isArray(value)) as [string, unknown[]][];
  const reasoning = typeof recommendation.reasoning === "string" ? recommendation.reasoning : null;

  return (
    <div className="flex flex-col gap-md" data-testid="recommendation-view">
      <dl className="grid grid-cols-2 gap-sm">
        {scalars.map(([key, value]) => (
          <Fragment key={key}>
            <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
              {humanize(key)}
            </dt>
            <dd className="font-mono text-body-sm text-text-primary">{formatValue(key, value)}</dd>
          </Fragment>
        ))}
      </dl>

      {lists.map(([key, values]) => (
        <div key={key}>
          <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
            {humanize(key)} ({values.length})
          </div>
          {values.length === 0 ? (
            <div className="mt-xs font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[NONE]</div>
          ) : (
            <ul className="mt-xs flex flex-col gap-2xs font-mono text-body-sm text-text-primary">
              {values.map((value, index) => (
                <li key={`${key}-${index}`}>{typeof value === "string" ? value : JSON.stringify(value)}</li>
              ))}
            </ul>
          )}
        </div>
      ))}

      {reasoning && (
        <div>
          <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Reasoning</div>
          <p className="mt-xs text-body-sm text-text-primary">{reasoning}</p>
        </div>
      )}
    </div>
  );
}
