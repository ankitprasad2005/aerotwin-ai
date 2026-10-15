import type { HTMLAttributes, ReactNode } from "react";

interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title?: ReactNode;
  /** Controls on the right of the title bar. */
  actions?: ReactNode;
  /** Set false for panels whose content (tables, graphs) should touch the edges. */
  padded?: boolean;
}

/** A dense Grafana-style panel: optional title bar over a bordered body. */
export function Panel({ title, actions, padded = true, children, className = "", ...props }: PanelProps) {
  return (
    <section className={`rounded-sm border border-line bg-panel ${className}`} {...props}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
          <h2 className="label text-muted">{title}</h2>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={padded ? "p-3" : ""}>{children}</div>
    </section>
  );
}
