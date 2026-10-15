/** Pure geometry for the hand-rolled SVG charts. Kept free of React so every edge case (empty
 * series, a single point, a flat line, NaN) is unit-testable. */

export interface Point {
  x: number;
  y: number;
}

export function finiteValues(values: readonly (number | null | undefined)[]): number[] {
  return values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
}

/** [min, max] of the finite values, widened so the range is never zero (a flat series would
 * otherwise divide by zero when scaled). An empty series gives [0, 1]. */
export function extent(values: readonly number[]): [number, number] {
  if (values.length === 0) return [0, 1];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) {
    const pad = Math.abs(min) * 0.05 || 1;
    return [min - pad, max + pad];
  }
  return [min, max];
}

export function scaleLinear(
  domain: [number, number],
  range: [number, number],
): (value: number) => number {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  if (d0 === d1) return () => (r0 + r1) / 2;
  return (value) => r0 + ((value - d0) / (d1 - d0)) * (r1 - r0);
}

export interface PlotBox {
  width: number;
  height: number;
  left: number;
  right: number;
  top: number;
  bottom: number;
}

/** Maps a series onto the inner plot box. Non-finite entries are dropped (they would produce
 * "NaN" in the path); a single point is centred horizontally. Returns the points together with the
 * y-domain used so axes can share it. */
export function seriesPoints(
  values: readonly (number | null | undefined)[],
  box: PlotBox,
  domain?: [number, number],
): { points: Point[]; indices: number[]; domain: [number, number] } {
  const indices: number[] = [];
  const finite: number[] = [];
  values.forEach((value, index) => {
    if (typeof value === "number" && Number.isFinite(value)) {
      indices.push(index);
      finite.push(value);
    }
  });
  const yDomain = domain ?? extent(finite);
  const x0 = box.left;
  const x1 = box.width - box.right;
  const y = scaleLinear(yDomain, [box.height - box.bottom, box.top]);
  const lastIndex = Math.max(1, values.length - 1);
  const x = scaleLinear([0, lastIndex], [x0, x1]);
  const points = finite.map((value, i) => ({
    x: finite.length === 1 ? (x0 + x1) / 2 : x(indices[i]),
    y: y(value),
  }));
  return { points, indices, domain: yDomain };
}

const fmt = (n: number) => (Math.round(n * 100) / 100).toString();

export function linePath(points: readonly Point[]): string {
  if (points.length === 0) return "";
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${fmt(p.x)} ${fmt(p.y)}`).join(" ");
}

export function areaPath(points: readonly Point[], baseline: number): string {
  if (points.length === 0) return "";
  const first = points[0];
  const last = points[points.length - 1];
  return `${linePath(points)} L${fmt(last.x)} ${fmt(baseline)} L${fmt(first.x)} ${fmt(baseline)} Z`;
}

/** Round, human-friendly tick values spanning [min, max]. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || count < 1) return [];
  if (min === max) return [min];
  const span = max - min;
  const rawStep = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const step = (residual >= 5 ? 10 : residual >= 2 ? 5 : 2) * magnitude;
  const ticks: number[] = [];
  for (let tick = Math.ceil(min / step) * step; tick <= max + step * 1e-9; tick += step) {
    ticks.push(Math.round(tick / step) * step);
  }
  return ticks;
}

/** Point on a circle; angles are in degrees, 0 = 3 o'clock, increasing clockwise (SVG y axis). */
export function polar(cx: number, cy: number, r: number, degrees: number): Point {
  const radians = (degrees * Math.PI) / 180;
  return { x: cx + r * Math.cos(radians), y: cy + r * Math.sin(radians) };
}

export function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  const start = polar(cx, cy, r, startDeg);
  const end = polar(cx, cy, r, endDeg);
  const largeArc = Math.abs(endDeg - startDeg) > 180 ? 1 : 0;
  return `M${fmt(start.x)} ${fmt(start.y)} A${r} ${r} 0 ${largeArc} 1 ${fmt(end.x)} ${fmt(end.y)}`;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
