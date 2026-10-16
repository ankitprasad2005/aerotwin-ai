// Response types of the generic data explorer (/api/data/*). Type-only, excluded from coverage.

export type ExplorerColumnType = "text" | "integer" | "number" | "boolean" | "date" | "datetime" | "json" | "id";

export interface ExplorerColumn {
  name: string;
  label: string;
  type: ExplorerColumnType;
  unit: string | null;
}

/** GET /api/data/catalog: one browsable table. New datasets appear here without any UI change. */
export interface CatalogEntry {
  key: string;
  title: string;
  category: string;
  description: string;
  row_count: number;
  last_refreshed: string | null;
  columns: ExplorerColumn[];
}

export type ExplorerRow = Record<string, unknown>;

/** GET /api/data/{key}/rows */
export interface ExplorerPage {
  total: number;
  rows: ExplorerRow[];
}
