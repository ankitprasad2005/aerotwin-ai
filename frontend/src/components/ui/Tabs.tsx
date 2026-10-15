import { useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabDef<K extends string> {
  key: K;
  label: string;
  /** Small count/badge shown after the label. */
  badge?: ReactNode;
}

interface TabsProps<K extends string> {
  tabs: readonly TabDef<K>[];
  active: K;
  onChange: (key: K) => void;
  label: string;
}

/** Accessible tab strip (WAI-ARIA tabs pattern): roving tabindex, arrow keys, Home/End. The caller
 * renders the active panel itself. */
export function Tabs<K extends string>({ tabs, active, onChange, label }: TabsProps<K>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = tabs.findIndex((tab) => tab.key === active);
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    onChange(tabs[next].key);
    refs.current[next]?.focus();
  }

  return (
    <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="flex gap-1 border-b border-line">
      {tabs.map((tab, index) => {
        const selected = tab.key === active;
        return (
          <button
            key={tab.key}
            ref={(element) => {
              refs.current[index] = element;
            }}
            type="button"
            role="tab"
            id={`tab-${tab.key}`}
            aria-selected={selected}
            aria-controls={`tabpanel-${tab.key}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.key)}
            className={`-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium ${
              selected ? "border-accent text-accent" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {tab.label}
            {tab.badge !== undefined && tab.badge !== null && (
              <span className="rounded-sm bg-line px-1 font-mono text-2xs text-muted">{tab.badge}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`tabpanel-${id}`} aria-labelledby={`tab-${id}`} tabIndex={0}>
      {children}
    </div>
  );
}
