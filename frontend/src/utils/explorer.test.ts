import { describe, expect, it } from "vitest";
import type { ExplorerColumn } from "../types/explorer";
import { expandedText, formatCell, groupByCategory, isWide, queryFromParams, rowsQueryString } from "./explorer";

const col = (type: ExplorerColumn["type"]): ExplorerColumn => ({ name: "c", label: "C", type, unit: null });
const base = { q: "", sort: "", order: "asc" as const, filters: {}, page: 1 };

describe("rowsQueryString", () => {
  it("pages from the 1-based page number", () => {
    expect(rowsQueryString({ ...base, page: 3 })).toBe("limit=50&offset=100");
  });

  it("adds search, sort and filters, skipping empty filters", () => {
    const qs = rowsQueryString({ q: "ind", sort: "airline", order: "desc", filters: { origin: "DEL", empty: "" }, page: 1 });
    expect(new URLSearchParams(qs).get("q")).toBe("ind");
    expect(new URLSearchParams(qs).get("sort")).toBe("airline");
    expect(new URLSearchParams(qs).get("order")).toBe("desc");
    expect(new URLSearchParams(qs).get("filter.origin")).toBe("DEL");
    expect(qs).not.toContain("empty");
  });

  it("omits paging for exports", () => {
    expect(rowsQueryString({ ...base, q: "x" }, false)).toBe("q=x");
    expect(rowsQueryString(base, false)).toBe("");
  });
});

describe("queryFromParams", () => {
  it("reads the URL state", () => {
    const query = queryFromParams(new URLSearchParams("q=a&sort=s&order=desc&page=2&f.origin=DEL&f.x="));
    expect(query).toEqual({ q: "a", sort: "s", order: "desc", filters: { origin: "DEL" }, page: 2 });
  });

  it("falls back to defaults for junk", () => {
    expect(queryFromParams(new URLSearchParams("page=abc&order=up"))).toEqual(base);
    expect(queryFromParams(new URLSearchParams("page=-4")).page).toBe(1);
  });
});

describe("groupByCategory", () => {
  it("keeps the backend order", () => {
    const entry = (key: string, category: string) => ({ key, category }) as never;
    const groups = groupByCategory([entry("a", "X"), entry("b", "Y"), entry("c", "X")]);
    expect(groups.map((g) => [g.category, g.entries.length])).toEqual([["X", 2], ["Y", 1]]);
  });
});

describe("cell formatting", () => {
  it("formats by column type", () => {
    expect(formatCell(null, col("text"))).toBe("—");
    expect(formatCell(undefined, col("text"))).toBe("—");
    expect(formatCell({ a: 1 }, col("json"))).toBe('{"a":1}');
    expect(formatCell(true, col("boolean"))).toBe("yes");
    expect(formatCell(false, col("boolean"))).toBe("no");
    expect(formatCell(1234.5, col("number"))).toBe("1,234.5");
    expect(formatCell("2026-10-15T08:00:00Z", col("datetime"))).toContain("Oct");
    expect(formatCell("abc", col("text"))).toBe("abc");
  });

  it("flags wide and nested values", () => {
    expect(isWide("x".repeat(61), col("text"))).toBe(true);
    expect(isWide("short", col("text"))).toBe(false);
    expect(isWide(["a"], col("json"))).toBe(true);
    expect(isWide(null, col("json"))).toBe(false);
    expect(isWide(5, col("number"))).toBe(false);
  });

  it("pretty-prints the expanded value", () => {
    expect(expandedText({ a: 1 }, col("json"))).toBe('{\n  "a": 1\n}');
    expect(expandedText(null, col("text"))).toBe("—");
    expect(expandedText("hello", col("text"))).toBe("hello");
  });
});
