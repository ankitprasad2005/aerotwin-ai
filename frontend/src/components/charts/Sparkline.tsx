import { areaPath, linePath, seriesPoints } from "../../utils/chart";

export type Tone = "accent" | "ok" | "warn" | "bad" | "muted";

export const TONE_VAR: Record<Tone, string> = {
  accent: "var(--c-accent)",
  ok: "var(--c-ok)",
  warn: "var(--c-warn)",
  bad: "var(--c-bad)",
  muted: "var(--c-muted)",
};

interface SparklineProps {
  values: readonly (number | null | undefined)[];
  width?: number;
  height?: number;
  tone?: Tone;
  /** Accessible name, e.g. "Runs per day, last 14 days". */
  label: string;
}

/** A tiny trend line with a soft area fill and an end-point dot. Renders a flat dashed baseline
 * instead of nothing when there is no data, so the layout does not jump. */
export function Sparkline({ values, width = 80, height = 24, tone = "accent", label }: SparklineProps) {
  const box = { width, height, left: 2, right: 3, top: 3, bottom: 3 };
  const { points } = seriesPoints(values, box);
  const color = TONE_VAR[tone];

  return (
    <svg
      role="img"
      aria-label={points.length === 0 ? `${label}: no data` : label}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="shrink-0"
    >
      {points.length === 0 ? (
        <line
          data-testid="sparkline-empty"
          x1={2}
          x2={width - 2}
          y1={height / 2}
          y2={height / 2}
          stroke={TONE_VAR.muted}
          strokeDasharray="2 3"
          strokeOpacity={0.6}
        />
      ) : (
        <>
          {points.length > 1 && <path d={areaPath(points, height - box.bottom)} fill={color} fillOpacity={0.12} />}
          <path
            data-testid="sparkline-line"
            d={points.length > 1 ? linePath(points) : `M${points[0].x - 3} ${points[0].y} L${points[0].x + 3} ${points[0].y}`}
            fill="none"
            stroke={color}
            strokeWidth={1.5}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r={2} fill={color} />
        </>
      )}
    </svg>
  );
}
