import type { HTMLAttributes } from "react";

export function Panel({ children, className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`bg-surface border border-border ${className}`} {...props}>
      {children}
    </div>
  );
}
