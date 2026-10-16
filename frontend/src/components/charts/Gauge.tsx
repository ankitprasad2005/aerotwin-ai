import { arcPath, clamp, polar } from "../../utils/chart";
import { formatScore } from "../../utils/format";
import { TONE_VAR, type Tone } from "./Sparkline";

interface GaugeProps {
  /** 0..100, or null when there is no score (decisions made before weighted scoring). */
  value: number | null;
  /** Zone boundaries: below `review` is red, below `recommend` amber, otherwise green. */
  thresholds?: { review: number; recommend: number };
  label: string;
  size?: number;
}

const START = 180;
const END = 360;

function angleFor(value: number): number {
  return START + (clamp(value, 0, 100) / 100) * (END - START);
}

export function toneForScore(value: number, thresholds: { review: number; recommend: number }): Tone {
  if (value >= thresholds.recommend) return "ok";
  if (value >= thresholds.review) return "warn";
  return "bad";
}

/** A half-circle score gauge on a 0-100 scale, coloured by the decision thresholds. */
export function Gauge({ value, thresholds = { review: 66, recommend: 76 }, label, size = 160 }: GaugeProps) {
  const cx = 80;
  const cy = 78;
  const r = 62;
  const hasValue = typeof value === "number" && Number.isFinite(value);
  const tone = hasValue ? toneForScore(value, thresholds) : "muted";
  const needle = hasValue ? polar(cx, cy, r - 14, angleFor(value)) : null;

  return (
    <svg
      role="img"
      aria-label={hasValue ? `${label}: ${formatScore(value)} out of 100` : `${label}: no score`}
      viewBox="0 0 160 100"
      width={size}
      height={(size * 100) / 160}
      data-testid="gauge"
    >
      <path d={arcPath(cx, cy, r, START, END)} fill="none" stroke="var(--c-line)" strokeWidth={10} strokeLinecap="round" />
      {hasValue && value > 0 && (
        <path
          data-testid="gauge-fill"
          d={arcPath(cx, cy, r, START, angleFor(value))}
          fill="none"
          stroke={TONE_VAR[tone]}
          strokeWidth={10}
          strokeLinecap="round"
        />
      )}
      {[thresholds.review, thresholds.recommend].map((threshold) => {
        const outer = polar(cx, cy, r + 8, angleFor(threshold));
        const inner = polar(cx, cy, r - 8, angleFor(threshold));
        return (
          <line
            key={threshold}
            data-testid="gauge-tick"
            x1={outer.x}
            y1={outer.y}
            x2={inner.x}
            y2={inner.y}
            stroke="var(--c-muted)"
            strokeWidth={1}
          />
        );
      })}
      {needle && <circle cx={needle.x} cy={needle.y} r={3} fill="#f1f5f9" />}
      <text x={cx} y={cy - 4} textAnchor="middle" fontSize={26} fontWeight={600} fill={hasValue ? "#f1f5f9" : "var(--c-muted)"}>
        {formatScore(value)}
      </text>
      <text x={cx} y={cy + 12} textAnchor="middle" fontSize={9} fill="var(--c-muted)">
        {`of 100 · review ${thresholds.review} · recommend ${thresholds.recommend}`}
      </text>
    </svg>
  );
}
