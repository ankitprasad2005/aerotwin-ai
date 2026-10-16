import { Fragment, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { exportUrl, useCatalog, useExplorerRows } from "../../api/useExplorer";
import type { CatalogEntry, ExplorerColumn } from "../../types/explorer";
import {
  FILTER_PREFIX,
  PAGE_SIZE,
  expandedText,
  formatCell,
  groupByCategory,
  isWide,
  queryFromParams,
  type ExplorerQuery,
} from "../../utils/explorer";
import { formatDateTime, formatNumber } from "../../utils/format";
import { Button } from "../ui/Button";
import { Panel } from "../ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../ui/States";

const DEBOUNCE_MS = 300;

/** A text input that reports its value to the URL after the user pauses typing. */
function DebouncedInput({
  value,
  onCommit,
  ...props
}: { value: string; onCommit: (value: string) => void } & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  useEffect(() => {
    if (draft === value) return;
    const timer = setTimeout(() => onCommit(draft), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [draft, value, onCommit]);
  return <input {...props} className={`field ${props.className ?? ""}`} value={draft} onChange={(event) => setDraft(event.target.value)} />;
}

function CategoryList({
  groups,
  active,
  onSelect,
}: {
  groups: { category: string; entries: CatalogEntry[] }[];
  active: string;
  onSelect: (category: string) => void;
}) {
  return (
    <nav aria-label="Categories">
      <ul className="flex flex-wrap gap-1 lg:flex-col">
        {groups.map(({ category, entries }) => (
          <li key={category}>
            <button
              type="button"
              aria-current={category === active ? "true" : undefined}
              onClick={() => onSelect(category)}
              className={`flex w-full items-center justify-between gap-2 rounded-sm border px-2 py-1 text-left text-sm ${
                category === active ? "border-accent text-accent" : "border-line text-ink hover:bg-panel-raised"
              }`}
            >
              <span>{category}</span>
              <span className="rounded-sm bg-line px-1 font-mono text-2xs text-muted">{entries.length}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function DatasetList({ entries, active, onSelect }: { entries: CatalogEntry[]; active: string | null; onSelect: (key: string) => void }) {
  return (
    <nav aria-label="Datasets">
      <ul className="flex flex-wrap gap-1 lg:flex-col">
        {entries.map((entry) => (
          <li key={entry.key}>
            <button
              type="button"
              aria-current={entry.key === active ? "true" : undefined}
              onClick={() => onSelect(entry.key)}
              title={entry.description}
              className={`flex w-full items-center justify-between gap-2 rounded-sm border px-2 py-1 text-left text-sm ${
                entry.key === active ? "border-accent bg-panel-raised text-ink-strong" : "border-line text-ink hover:bg-panel-raised"
              }`}
            >
              <span className="min-w-0 break-words">{entry.title}</span>
              <span className="font-mono text-2xs text-muted">{formatNumber(entry.row_count)}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function ExpandedRow({ row, columns }: { row: Record<string, unknown>; columns: ExplorerColumn[] }) {
  return (
    <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-2" data-testid="row-detail">
      {columns.map((column) => (
        <div key={column.name} className="min-w-0">
          <dt className="label text-muted">{column.label}</dt>
          <dd>
            <pre className="whitespace-pre-wrap break-words font-mono text-xs text-ink">{expandedText(row[column.name], column)}</pre>
          </dd>
        </div>
      ))}
    </dl>
  );
}

function DataTable({
  entry,
  query,
  rows,
  onSort,
}: {
  entry: CatalogEntry;
  query: ExplorerQuery;
  rows: Record<string, unknown>[];
  onSort: (column: string) => void;
}) {
  const [open, setOpen] = useState<number | null>(null);
  useEffect(() => setOpen(null), [entry.key, query.page, query.q, query.sort, query.order]);
  const columns = entry.columns;
  return (
    <div className="max-w-full overflow-x-auto" data-testid="explorer-table">
      <table className="w-full min-w-max border-collapse text-sm">
        <thead>
          <tr className="border-b border-line text-left">
            <th className="w-8 px-1" aria-label="Expand" />
            {columns.map((column) => {
              const sorted = query.sort === column.name;
              return (
                <th
                  key={column.name}
                  scope="col"
                  aria-sort={sorted ? (query.order === "desc" ? "descending" : "ascending") : "none"}
                  className="whitespace-nowrap px-2 py-1.5"
                >
                  <button type="button" className="label inline-flex items-center gap-1 text-muted hover:text-ink" onClick={() => onSort(column.name)}>
                    {column.label}
                    {column.unit && <span className="font-normal normal-case text-faint">({column.unit})</span>}
                    <span aria-hidden="true">{sorted ? (query.order === "desc" ? "▼" : "▲") : ""}</span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const expanded = open === index;
            return (
              <Fragment key={index}>
                <tr className="border-b border-line/60 align-top hover:bg-panel-raised">
                  <td className="px-1">
                    <button
                      type="button"
                      aria-expanded={expanded}
                      aria-label={expanded ? "Collapse row" : "Expand row"}
                      className="px-1 text-muted hover:text-ink"
                      onClick={() => setOpen(expanded ? null : index)}
                    >
                      {expanded ? "▾" : "▸"}
                    </button>
                  </td>
                  {columns.map((column) => {
                    const text = formatCell(row[column.name], column);
                    const wide = isWide(row[column.name], column);
                    return (
                      <td
                        key={column.name}
                        title={wide ? text : undefined}
                        className={`px-2 py-1 ${
                          column.type === "text" || column.type === "id" || column.type === "json" ? "" : "whitespace-nowrap font-mono"
                        } ${wide ? "max-w-[22rem] truncate" : "whitespace-nowrap"}`}
                      >
                        {text}
                      </td>
                    );
                  })}
                </tr>
                {expanded && (
                  <tr className="border-b border-line bg-canvas">
                    <td colSpan={columns.length + 1} className="px-3 py-2">
                      <div className="max-w-[calc(100vw-3rem)] lg:max-w-none">
                        <ExpandedRow row={row} columns={columns} />
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TableView({
  entry,
  query,
  update,
}: {
  entry: CatalogEntry;
  query: ExplorerQuery;
  update: (patch: Record<string, string | null>) => void;
}) {
  const [showFilters, setShowFilters] = useState(Object.keys(query.filters).length > 0);
  const { data, isLoading, isError, error, refetch, isFetching } = useExplorerRows(entry.key, query);
  const total = data?.total ?? 0;
  const first = total === 0 ? 0 : (query.page - 1) * PAGE_SIZE + 1;
  const last = Math.min(query.page * PAGE_SIZE, total);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const onSort = (column: string) => {
    if (query.sort !== column) update({ sort: column, order: "asc", page: null });
    else if (query.order === "asc") update({ sort: column, order: "desc", page: null });
    else update({ sort: null, order: null, page: null });
  };

  return (
    <Panel
      title={entry.title}
      data-testid="explorer-panel"
      actions={
        <a
          href={exportUrl(entry.key, query)}
          download
          className="inline-flex items-center rounded-sm border border-line-strong px-3 py-1.5 text-sm font-medium text-ink hover:border-muted hover:bg-panel-raised"
        >
          Export CSV
        </a>
      }
    >
      <p className="text-sm text-muted">{entry.description}</p>
      <p className="mt-1 text-xs text-muted" data-testid="explorer-meta">
        <span className="font-mono text-ink">{formatNumber(total)}</span> {total === 1 ? "row" : "rows"}
        {Object.keys(query.filters).length > 0 || query.q ? " match" : ""}
        {" · "}
        {entry.last_refreshed ? `Last refreshed ${formatDateTime(entry.last_refreshed)}` : "No refresh recorded"}
      </p>

      <div className="mt-3 flex flex-wrap items-end gap-2">
        <div className="flex min-w-[200px] flex-1 flex-col gap-1">
          <label htmlFor="explorer-search" className="label text-muted">
            Search
          </label>
          <DebouncedInput
            id="explorer-search"
            type="search"
            value={query.q}
            placeholder={`Search ${entry.title.toLowerCase()}`}
            onCommit={(value) => update({ q: value || null, page: null })}
          />
        </div>
        <Button variant="ghost" aria-expanded={showFilters} onClick={() => setShowFilters((v) => !v)}>
          Filters{Object.keys(query.filters).length > 0 ? ` (${Object.keys(query.filters).length})` : ""}
        </Button>
      </div>

      {showFilters && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3" data-testid="explorer-filters">
          {entry.columns.map((column) => (
            <div key={column.name} className="flex min-w-0 flex-col gap-1">
              <label htmlFor={`filter-${column.name}`} className="label text-muted">
                {column.label}
              </label>
              <DebouncedInput
                id={`filter-${column.name}`}
                value={query.filters[column.name] ?? ""}
                placeholder={column.type === "boolean" ? "true / false" : column.type === "date" ? "YYYY-MM-DD" : "contains…"}
                onCommit={(value) => update({ [`${FILTER_PREFIX}${column.name}`]: value || null, page: null })}
              />
            </div>
          ))}
        </div>
      )}

      <div className="mt-3" aria-live="polite" aria-busy={isFetching}>
        {isLoading && <LoadingState label="Loading rows…" />}
        {isError && <ErrorState title="Could not load the rows" error={error} onRetry={() => void refetch()} />}
        {data && data.rows.length === 0 && (
          <EmptyState
            title={query.q || Object.keys(query.filters).length > 0 ? "No rows match" : "This dataset has no rows yet"}
            hint={query.q || Object.keys(query.filters).length > 0 ? "Clear the search or filters." : "Refresh its source on the Overview tab."}
          />
        )}
        {data && data.rows.length > 0 && <DataTable entry={entry} query={query} rows={data.rows} onSort={onSort} />}
      </div>

      {data && total > PAGE_SIZE && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="text-muted" data-testid="explorer-range">
            {first}–{last} of {formatNumber(total)}
          </span>
          <div className="flex items-center gap-2">
            <Button variant="ghost" disabled={query.page <= 1} onClick={() => update({ page: query.page - 1 <= 1 ? null : String(query.page - 1) })}>
              Previous
            </Button>
            <span className="text-xs text-muted">
              Page {query.page} of {pages}
            </span>
            <Button variant="ghost" disabled={query.page >= pages} onClick={() => update({ page: String(query.page + 1) })}>
              Next
            </Button>
          </div>
        </div>
      )}
    </Panel>
  );
}

/** Browse every dataset the backend exposes, driven purely by /api/data/catalog. State lives in the URL
 * (?tab=explorer&dataset=key&q=...&sort=...&order=...&f.<column>=...&page=n). */
export function DataExplorer() {
  const catalog = useCatalog();
  const [params, setParams] = useSearchParams();

  const update = (patch: Record<string, string | null>) =>
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        for (const [name, value] of Object.entries(patch)) {
          if (value === null) next.delete(name);
          else next.set(name, value);
        }
        return next;
      },
      { replace: true },
    );

  if (catalog.isLoading) return <LoadingState label="Loading the data catalog…" />;
  if (catalog.isError) return <ErrorState title="Could not load the data catalog" error={catalog.error} onRetry={() => void catalog.refetch()} />;
  const entries = catalog.data ?? [];
  if (entries.length === 0) return <EmptyState title="No datasets are available" hint="The backend reports an empty data catalog." />;

  const groups = groupByCategory(entries);
  const requested = entries.find((entry) => entry.key === params.get("dataset"));
  const category = requested?.category ?? groups.find((g) => g.category === params.get("category"))?.category ?? groups[0].category;
  const inCategory = groups.find((g) => g.category === category)?.entries ?? [];
  const selected = requested ?? null;
  const query = queryFromParams(params);

  const selectCategory = (next: string) => {
    const clear = { dataset: null, q: null, sort: null, order: null, page: null };
    const filters = Object.fromEntries([...params.keys()].filter((k) => k.startsWith(FILTER_PREFIX)).map((k) => [k, null]));
    update({ ...clear, ...filters, category: next });
  };
  const selectDataset = (key: string) => {
    const filters = Object.fromEntries([...params.keys()].filter((k) => k.startsWith(FILTER_PREFIX)).map((k) => [k, null]));
    update({ ...filters, dataset: key, category: null, q: null, sort: null, order: null, page: null });
  };

  return (
    <div className="grid min-w-0 gap-3 lg:grid-cols-[11rem_15rem_minmax(0,1fr)]" data-testid="data-explorer">
      <div>
        <h2 className="label mb-1 text-muted">Categories</h2>
        <CategoryList groups={groups} active={category} onSelect={selectCategory} />
      </div>
      <div>
        <h2 className="label mb-1 text-muted">Datasets</h2>
        <DatasetList entries={inCategory} active={selected?.key ?? null} onSelect={selectDataset} />
      </div>
      <div className="min-w-0">
        {selected ? (
          <TableView key={selected.key} entry={selected} query={query} update={update} />
        ) : (
          <EmptyState title="Pick a dataset" hint="Choose a dataset from the list to browse its rows." />
        )}
      </div>
    </div>
  );
}
