import type { ReactNode } from "react";
import type { Verdict } from "../../types/api";
import { VERDICT_HELP, VERDICT_LABEL } from "../../utils/decision";
import { Tooltip } from "./Tooltip";

export type BadgeTone = "ok" | "warn" | "bad" | "accent" | "muted";

const TONE_CLASS: Record<BadgeTone, string> = {
  ok: "border-ok/40 bg-ok/10 text-ok",
  warn: "border-warn/40 bg-warn/10 text-warn",
  bad: "border-bad/40 bg-bad/10 text-bad",
  accent: "border-accent/40 bg-accent/10 text-accent",
  muted: "border-line-strong bg-panel-raised text-muted",
};

export function Badge({ tone = "muted", children, title }: { tone?: BadgeTone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-sm border px-1.5 py-px text-2xs font-semibold uppercase tracking-wide ${TONE_CLASS[tone]}`}
    >
      {children}
    </span>
  );
}

const VERDICT_TONE: Record<Verdict, BadgeTone> = { RECOMMEND: "ok", REVIEW: "warn", REJECT: "bad" };

/** The decision verdict. A decision made before weighted scoring has none, so null shows a dash. */
export function VerdictBadge({ verdict, withHelp = false }: { verdict: Verdict | null | undefined; withHelp?: boolean }) {
  if (!verdict) return <span className="text-muted">—</span>;
  const badge = <Badge tone={VERDICT_TONE[verdict]}>{VERDICT_LABEL[verdict]}</Badge>;
  return withHelp ? <Tooltip content={VERDICT_HELP[verdict]}>{badge}</Tooltip> : badge;
}

const RISK_TONE: Record<string, BadgeTone> = { LOW: "ok", MEDIUM: "warn", HIGH: "bad" };

export function RiskBadge({ risk }: { risk: string | null | undefined }) {
  if (!risk) return <span className="text-muted">—</span>;
  return <Badge tone={RISK_TONE[risk] ?? "muted"}>{risk}</Badge>;
}

/** A small mono chip, e.g. for a cited evidence id. */
export function Chip({ children, title, tone = "muted" }: { children: ReactNode; title?: string; tone?: BadgeTone }) {
  return (
    <span
      title={title}
      className={`inline-block max-w-[180px] truncate rounded-sm border px-1.5 py-px align-middle font-mono text-2xs ${TONE_CLASS[tone]}`}
    >
      {children}
    </span>
  );
}

/** Reliability 0..1 as a thin bar plus a percentage. */
export function ReliabilityBar({ value }: { value: number }) {
  const fraction = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
  const color = fraction >= 0.8 ? "bg-ok" : fraction >= 0.5 ? "bg-accent" : "bg-warn";
  return (
    <span className="inline-flex items-center gap-1.5" title={`Reliability ${Math.round(fraction * 100)}%`}>
      <span
        role="meter"
        aria-label="Reliability"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(fraction * 100)}
        className="inline-block h-1.5 w-14 overflow-hidden rounded-sm bg-line"
      >
        <span className={`block h-full ${color}`} style={{ width: `${fraction * 100}%` }} />
      </span>
      <span className="font-mono text-2xs text-muted">{Math.round(fraction * 100)}%</span>
    </span>
  );
}
