import { clamp } from "../../utils/chart";
import { TONE_VAR, type Tone } from "./Sparkline";

export interface BarItem {
  key: string;
  label: string;
  /** 0..1; clamped. */
  fraction: number;
  /** Right-hand text, e.g. "0.62 × 0.30 = +18.6". */
  detail?: string;
  tone?: Tone;
  /** Longer explanation shown as a native tooltip. */
  hint?: string;
}

/** Horizontal bars, one per row: label, track with fill, and an optional detail string. Used for
 * the decision's per-factor breakdown. */
export function BreakdownBars({ items, label }: { items: readonly BarItem[]; label: string }) {
  if (items.length === 0) {
    return (
      <p data-testid="breakdown-empty" className="text-sm text-muted">
        No breakdown available.
      </p>
    );
  }
  return (
    <ul aria-label={label} className="flex flex-col gap-2">
      {items.map((item) => {
        const fraction = Number.isFinite(item.fraction) ? clamp(item.fraction, 0, 1) : 0;
        return (
          <li key={item.key} title={item.hint} className="grid grid-cols-[96px_1fr_auto] items-center gap-2 text-sm">
            <span className="truncate text-muted">{item.label}</span>
            <div
              role="meter"
              aria-label={item.label}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(fraction * 100)}
              className="h-2 overflow-hidden rounded-sm bg-line"
            >
              <div
                data-testid="bar-fill"
                className="h-full"
                style={{ width: `${fraction * 100}%`, background: TONE_VAR[item.tone ?? "accent"] }}
              />
            </div>
            <span className="min-w-[88px] text-right font-mono text-xs text-ink">{item.detail ?? ""}</span>
          </li>
        );
      })}
    </ul>
  );
}

export interface StackSegment {
  key: string;
  label: string;
  value: number;
  tone: Tone;
}

/** One stacked bar splitting a total into labelled segments, with a legend. */
export function StackedBar({ segments, label }: { segments: readonly StackSegment[]; label: string }) {
  const safe = segments.map((s) => ({ ...s, value: Number.isFinite(s.value) && s.value > 0 ? s.value : 0 }));
  const total = safe.reduce((sum, s) => sum + s.value, 0);
  return (
    <div>
      <div
        role="img"
        aria-label={total === 0 ? `${label}: no data` : `${label}: ${safe.map((s) => `${s.label} ${s.value}`).join(", ")}`}
        className="flex h-3 overflow-hidden rounded-sm bg-line"
      >
        {total > 0 &&
          safe
            .filter((s) => s.value > 0)
            .map((s) => (
              <div
                key={s.key}
                data-testid="stack-segment"
                title={`${s.label}: ${s.value}`}
                style={{ width: `${(s.value / total) * 100}%`, background: TONE_VAR[s.tone] }}
              />
            ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {safe.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ background: TONE_VAR[s.tone] }} />
            {s.label} <span className="font-mono text-ink">{s.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
