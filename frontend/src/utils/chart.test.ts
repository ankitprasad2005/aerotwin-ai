import { describe, expect, it } from "vitest";
import {
  areaPath,
  arcPath,
  clamp,
  extent,
  finiteValues,
  linePath,
  niceTicks,
  polar,
  scaleLinear,
  seriesPoints,
} from "./chart";

const box = { width: 100, height: 50, left: 0, right: 0, top: 0, bottom: 0 };

describe("finiteValues", () => {
  it("drops null, undefined, NaN and infinities", () => {
    expect(finiteValues([1, null, undefined, Number.NaN, Infinity, 2])).toEqual([1, 2]);
  });
});

describe("extent", () => {
  it("returns min and max", () => expect(extent([3, 1, 2])).toEqual([1, 3]));
  it("gives an empty series a unit range", () => expect(extent([])).toEqual([0, 1]));
  it("widens a flat series so it can be scaled", () => {
    const [lo, hi] = extent([5, 5, 5]);
    expect(lo).toBeLessThan(5);
    expect(hi).toBeGreaterThan(5);
  });
  it("widens a flat zero series", () => expect(extent([0, 0])).toEqual([-1, 1]));
});

describe("scaleLinear", () => {
  it("maps the domain onto the range", () => {
    const scale = scaleLinear([0, 10], [0, 100]);
    expect(scale(5)).toBe(50);
    expect(scale(0)).toBe(0);
  });
  it("supports inverted ranges (SVG y axis)", () => expect(scaleLinear([0, 10], [100, 0])(2)).toBe(80));
  it("returns the midpoint for a degenerate domain", () => expect(scaleLinear([3, 3], [0, 10])(3)).toBe(5));
});

describe("seriesPoints", () => {
  it("spreads points across the width, highest value at the top", () => {
    const { points } = seriesPoints([0, 10, 5], box);
    expect(points.map((p) => p.x)).toEqual([0, 50, 100]);
    expect(points[1].y).toBe(0);
    expect(points[0].y).toBe(50);
  });
  it("returns nothing for an empty series", () => {
    expect(seriesPoints([], box).points).toEqual([]);
  });
  it("centres a single point", () => {
    const { points } = seriesPoints([7], box);
    expect(points).toHaveLength(1);
    expect(points[0].x).toBe(50);
  });
  it("skips non-finite values but keeps x positions of the rest", () => {
    const { points, indices } = seriesPoints([1, Number.NaN, 3], box);
    expect(indices).toEqual([0, 2]);
    expect(points.map((p) => p.x)).toEqual([0, 100]);
  });
  it("draws a flat series through the middle", () => {
    const { points } = seriesPoints([4, 4, 4], box);
    expect(new Set(points.map((p) => p.y)).size).toBe(1);
    expect(points[0].y).toBeCloseTo(25);
  });
  it("honours padding and an explicit domain", () => {
    const { points, domain } = seriesPoints([5], { ...box, left: 10, right: 10, top: 5, bottom: 5 }, [0, 10]);
    expect(domain).toEqual([0, 10]);
    expect(points[0]).toEqual({ x: 50, y: 25 });
  });
});

describe("paths", () => {
  it("linePath is empty for no points and M/L otherwise", () => {
    expect(linePath([])).toBe("");
    expect(linePath([{ x: 0, y: 1 }, { x: 2.123, y: 3 }])).toBe("M0 1 L2.12 3");
  });
  it("areaPath closes down to the baseline", () => {
    expect(areaPath([], 10)).toBe("");
    expect(areaPath([{ x: 0, y: 1 }, { x: 5, y: 2 }], 10)).toBe("M0 1 L5 2 L5 10 L0 10 Z");
  });
});

describe("niceTicks", () => {
  it("produces round ticks within the range", () => {
    expect(niceTicks(0, 100, 4)).toEqual([0, 50, 100]);
    const ticks = niceTicks(2.1, 2.9, 4);
    expect(ticks.every((t) => t >= 2.1 && t <= 2.9)).toBe(true);
    expect(ticks.length).toBeGreaterThan(1);
  });
  it("handles equal bounds, bad input and a zero count", () => {
    expect(niceTicks(3, 3)).toEqual([3]);
    expect(niceTicks(Number.NaN, 3)).toEqual([]);
    expect(niceTicks(0, 1, 0)).toEqual([]);
  });
  it("picks steps for every magnitude bucket", () => {
    expect(niceTicks(0, 5, 10)).toContain(1);
    expect(niceTicks(0, 10, 10)).toContain(2);
    expect(niceTicks(0, 20, 10)).toContain(5);
    expect(niceTicks(0, 70, 10)).toContain(10);
  });
});

describe("polar and arcs", () => {
  it("polar maps degrees to coordinates", () => {
    const p = polar(0, 0, 10, 90);
    expect(p.x).toBeCloseTo(0);
    expect(p.y).toBeCloseTo(10);
  });
  it("arcPath uses the small-arc flag up to 180 degrees and the large-arc flag beyond", () => {
    expect(arcPath(0, 0, 10, 180, 360)).toContain("0 0 1");
    expect(arcPath(0, 0, 10, 0, 270)).toContain("0 1 1");
  });
});

describe("clamp", () => {
  it("bounds values", () => {
    expect(clamp(5, 0, 3)).toBe(3);
    expect(clamp(-1, 0, 3)).toBe(0);
    expect(clamp(2, 0, 3)).toBe(2);
  });
});
