import type { ReactNode } from "react";

export function MonoText({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`font-mono ${className}`}>{children}</span>;
}

export function Label({ children }: { children: ReactNode }) {
  return (
    <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">{children}</span>
  );
}
