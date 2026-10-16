import type { CatalogEntry, ExplorerColumn } from "../types/explorer";
import { DASH, formatDateTime } from "./format";

export const PAGE_SIZE = 50;
export const FILTER_PREFIX = "f.";

export interface ExplorerQuery {
  q: string;
  sort: string;
  order: "asc" | "desc";
  filters: Record<string, string>;
  page: number; // 1-based
}

/** The query string the backend expects (limit/offset/q/sort/order/filter.<column>). */
export function rowsQueryString(query: ExplorerQuery, paged = true): string {
  const params = new URLSearchParams();
  if (paged) {
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String((query.page - 1) * PAGE_SIZE));
  }
  if (query.q) params.set("q", query.q);
  if (query.sort) {
    params.set("sort", query.sort);
    params.set("order", query.order);
  }
  for (const [column, value] of Object.entries(query.filters)) {
    if (value) params.set(`filter.${column}`, value);
  }
  return params.toString();
}

/** Parses the page URL into a query; the filters live in `f.<column>` params. */
export function queryFromParams(params: URLSearchParams): ExplorerQuery {
  const filters: Record<string, string> = {};
  params.forEach((value, name) => {
    if (name.startsWith(FILTER_PREFIX) && value) filters[name.slice(FILTER_PREFIX.length)] = value;
  });
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  return {
    q: params.get("q") ?? "",
    sort: params.get("sort") ?? "",
    order: params.get("order") === "desc" ? "desc" : "asc",
    filters,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

/** Groups the catalog by category, keeping the backend's order. */
export function groupByCategory(catalog: CatalogEntry[]): { category: string; entries: CatalogEntry[] }[] {
  const groups = new Map<string, CatalogEntry[]>();
  for (const entry of catalog) groups.set(entry.category, [...(groups.get(entry.category) ?? []), entry]);
  return [...groups].map(([category, entries]) => ({ category, entries }));
}

/** True when a cell is too wide or nested to show inline, so the row offers an expanded view. */
export function isWide(value: unknown, column: ExplorerColumn): boolean {
  if (column.type === "json") return value !== null && value !== undefined;
  return typeof value === "string" && value.length > 60;
}

export function formatCell(value: unknown, column: ExplorerColumn): string {
  if (value === null || value === undefined) return DASH;
  if (column.type === "json") return JSON.stringify(value);
  if (column.type === "boolean") return value ? "yes" : "no";
  if (column.type === "datetime") return formatDateTime(String(value));
  if (typeof value === "number") return value.toLocaleString("en-US", { maximumFractionDigits: 4 });
  return String(value);
}

export function expandedText(value: unknown, column: ExplorerColumn): string {
  if (column.type === "json") return JSON.stringify(value, null, 2);
  return value === null || value === undefined ? DASH : String(value);
}
