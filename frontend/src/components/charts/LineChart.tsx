import { useState, type KeyboardEvent, type MouseEvent } from "react";
import { areaPath, linePath, niceTicks, seriesPoints, type PlotBox } from "../../utils/chart";
import { TONE_VAR, type Tone } from "./Sparkline";

export interface LineDatum {
  /** x-axis label, e.g. an ISO date. */
  x: string;
  y: number;
}

interface LineChartProps {
  data: readonly LineDatum[];
  label: string;
  tone?: Tone;
  height?: number;
  formatY?: (value: number) => string;
  formatX?: (x: string) => string;
}

const WIDTH = 560;
const identity = (value: string) => value;
const defaultY = (value: number) => String(Math.round(value * 100) / 100);

/** A responsive SVG line chart with a y grid, first/last x labels and a hover/keyboard readout. */
export function LineChart({
  data,
  label,
  tone = "accent",
  height = 160,
  formatY = defaultY,
  formatX = identity,
}: LineChartProps) {
  const [active, setActive] = useState<number | null>(null);
  const box: PlotBox = { width: WIDTH, height, left: 44, right: 10, top: 10, bottom: 22 };
  const { points, domain } = seriesPoints(
    data.map((d) => d.y),
    box,
  );
  const color = TONE_VAR[tone];

  if (data.length === 0 || points.length === 0) {
    return (
      <div
        role="img"
        aria-label={`${label}: no data`}
        data-testid="linechart-empty"
        style={{ height }}
        className="flex items-center justify-center rounded-sm border border-dashed border-line text-sm text-muted"
      >
        No data yet
      </div>
    );
  }

  const ticks = niceTicks(domain[0], domain[1], 3);
  const yFor = (value: number) =>
    box.height - box.bottom - ((value - domain[0]) / (domain[1] - domain[0] || 1)) * (box.height - box.bottom - box.top);
  const baseline = box.height - box.bottom;

  // Points skip non-finite values, so map them back to their datum for the readout.
  const finiteData = data.filter((d) => Number.isFinite(d.y));
  const activePoint = active !== null ? points[active] : null;
  const activeDatum = active !== null ? finiteData[active] : null;

  function nearestIndex(clientX: number, rect: DOMRect): number {
    const x = ((clientX - rect.left) / (rect.width || 1)) * WIDTH;
    let best = 0;
    points.forEach((point, index) => {
      if (Math.abs(point.x - x) < Math.abs(points[best].x - x)) best = index;
    });
    return best;
  }

  function onMove(event: MouseEvent<SVGSVGElement>) {
    setActive(nearestIndex(event.clientX, event.currentTarget.getBoundingClientRect()));
  }

  function onKey(event: KeyboardEvent<SVGSVGElement>) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      setActive((current) => Math.min(points.length - 1, (current ?? -1) + 1));
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      setActive((current) => Math.max(0, (current ?? points.length) - 1));
    } else if (event.key === "Escape") {
      setActive(null);
    }
  }

  const first = finiteData[0];
  const last = finiteData[finiteData.length - 1];

  return (
    <svg
      role="img"
      aria-label={`${label}, ${finiteData.length} points, from ${formatY(first.y)} to ${formatY(last.y)}`}
      tabIndex={0}
      viewBox={`0 0 ${WIDTH} ${height}`}
      className="w-full"
      style={{ height }}
      onMouseMove={onMove}
      onMouseLeave={() => setActive(null)}
      onBlur={() => setActive(null)}
      onKeyDown={onKey}
      data-testid="linechart"
    >
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={box.left} x2={WIDTH - box.right} y1={yFor(tick)} y2={yFor(tick)} stroke="var(--c-line)" />
          <text x={box.left - 6} y={yFor(tick) + 3} textAnchor="end" fontSize={10} fill="var(--c-muted)">
            {formatY(tick)}
          </text>
        </g>
      ))}
      {points.length > 1 && <path d={areaPath(points, baseline)} fill={color} fillOpacity={0.1} />}
      <path
        data-testid="linechart-line"
        d={linePath(points)}
        fill="none"
        stroke={color}
        strokeWidth={1.75}
        strokeLinejoin="round"
      />
      {points.length === 1 && <circle cx={points[0].x} cy={points[0].y} r={3} fill={color} />}
      <text x={box.left} y={height - 6} fontSize={10} fill="var(--c-muted)">
        {formatX(first.x)}
      </text>
      {finiteData.length > 1 && (
        <text x={WIDTH - box.right} y={height - 6} fontSize={10} textAnchor="end" fill="var(--c-muted)">
          {formatX(last.x)}
        </text>
      )}
      {activePoint && activeDatum && (
        <g data-testid="linechart-readout" pointerEvents="none">
          <line x1={activePoint.x} x2={activePoint.x} y1={box.top} y2={baseline} stroke="var(--c-muted)" strokeDasharray="3 3" />
          <circle cx={activePoint.x} cy={activePoint.y} r={3.5} fill={color} stroke="#0b0e14" strokeWidth={1.5} />
          <text
            x={activePoint.x > WIDTH / 2 ? activePoint.x - 8 : activePoint.x + 8}
            y={Math.max(box.top + 10, activePoint.y - 8)}
            fontSize={11}
            textAnchor={activePoint.x > WIDTH / 2 ? "end" : "start"}
            fill="#f1f5f9"
          >
            {`${formatX(activeDatum.x)}: ${formatY(activeDatum.y)}`}
          </text>
        </g>
      )}
    </svg>
  );
}
