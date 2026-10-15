import { normalizeGroup } from "../../utils/weights";
import { formatPercent } from "../../utils/format";

export interface WeightRowDef<K extends string> {
  key: K;
  label: string;
  help?: string;
}

/** A group of weight sliders with a numeric input each and the live share every weight will have
 * once the group is normalised (the engine divides by the group total, so only the ratios matter). */
export function WeightGroup<K extends string>({
  title,
  description,
  rows,
  values,
  onChange,
}: {
  title: string;
  description: string;
  rows: readonly WeightRowDef<K>[];
  values: Record<K, number>;
  onChange: (key: K, value: number) => void;
}) {
  const shares = normalizeGroup(values);
  const total = rows.reduce((sum, row) => sum + (Number.isFinite(values[row.key]) ? values[row.key] : 0), 0);

  return (
    <fieldset className="min-w-0 rounded-sm border border-line bg-panel p-3">
      <legend className="label px-1 text-muted">{title}</legend>
      <p className="mb-2 text-xs text-muted">{description}</p>
      <ul className="flex flex-col gap-2">
        {rows.map((row) => {
          const value = values[row.key];
          return (
            <li key={row.key} title={row.help} className="grid grid-cols-[110px_minmax(80px,1fr)_64px_52px] items-center gap-2 text-sm">
              <span className="truncate text-ink">{row.label}</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0}
                aria-label={`${row.label} weight slider`}
                onChange={(event) => onChange(row.key, Number(event.target.value))}
                className="h-1 w-full accent-[#38bdf8]"
              />
              <input
                type="number"
                min={0}
                step={0.05}
                value={Number.isFinite(value) ? value : ""}
                aria-label={`${row.label} weight`}
                onChange={(event) => onChange(row.key, event.target.value === "" ? Number.NaN : Number(event.target.value))}
                className="field w-full px-1.5 py-0.5 text-right font-mono"
              />
              <span className="text-right font-mono text-xs text-accent" data-testid={`share-${row.key}`}>
                {formatPercent(shares[row.key] * 100, 0)}
              </span>
            </li>
          );
        })}
      </ul>
      <div className="mt-2 flex justify-between border-t border-line pt-1.5 text-xs text-muted">
        <span>Raw total</span>
        <span className="font-mono" data-testid="weight-total">
          {total.toFixed(2)}
        </span>
      </div>
    </fieldset>
  );
}
