import { describe, expect, it } from "vitest";
import { makeStatsRun } from "../test/fixtures";
import { EMPTY_FILTERS, filterRuns, hasActiveFilters } from "./runs";

const runs = [
  makeStatsRun({ id: "1", objective: "Improve profitability", status: "COMPLETED" }),
  makeStatsRun({ id: "2", objective: "Cut fuel costs", status: "FAILED", decision: null }),
  makeStatsRun({
    id: "3",
    objective: "Protect load factor",
    status: "COMPLETED",
    decision: { summary: "Reduce DEL-BLR frequency", verdict: "REJECT", score: 30, expected_profit_impact: -1, risk: "HIGH" },
  }),
  makeStatsRun({
    id: "4",
    objective: "Old run",
    decision: { summary: "legacy", verdict: null, score: null, expected_profit_impact: 5, risk: null },
  }),
];

const ids = (list: { id: string }[]) => list.map((run) => run.id);

describe("filterRuns", () => {
  it("returns everything with empty filters", () => {
    expect(ids(filterRuns(runs, EMPTY_FILTERS))).toEqual(["1", "2", "3", "4"]);
  });
  it("filters by status", () => {
    expect(ids(filterRuns(runs, { ...EMPTY_FILTERS, status: "FAILED" }))).toEqual(["2"]);
  });
  it("filters by verdict", () => {
    expect(ids(filterRuns(runs, { ...EMPTY_FILTERS, verdict: "REJECT" }))).toEqual(["3"]);
    expect(ids(filterRuns(runs, { ...EMPTY_FILTERS, verdict: "RECOMMEND" }))).toEqual(["1"]);
  });
  it("filters runs without a verdict, including runs with no decision at all", () => {
    expect(ids(filterRuns(runs, { ...EMPTY_FILTERS, verdict: "NONE" }))).toEqual(["2", "4"]);
  });
  it("searches objective and decision summary, case-insensitively and trimmed", () => {
    expect(ids(filterRuns(runs, { ...EMPTY_FILTERS, query: "  FUEL " }))).toEqual(["2"]);
    expect(ids(filterRuns(runs, { ...EMPTY_FILTERS, query: "del-blr" }))).toEqual(["3"]);
  });
  it("combines filters", () => {
    expect(ids(filterRuns(runs, { status: "COMPLETED", verdict: "REJECT", query: "load" }))).toEqual(["3"]);
    expect(filterRuns(runs, { status: "FAILED", verdict: "REJECT", query: "" })).toEqual([]);
  });
  it("handles an empty list", () => {
    expect(filterRuns([], EMPTY_FILTERS)).toEqual([]);
  });
});

describe("hasActiveFilters", () => {
  it("detects any active filter", () => {
    expect(hasActiveFilters(EMPTY_FILTERS)).toBe(false);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, query: "   " })).toBe(false);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, status: "FAILED" })).toBe(true);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, verdict: "NONE" })).toBe(true);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, query: "x" })).toBe(true);
  });
});
