export function Pulse({ active, className = "bg-ok" }: { active: boolean; className?: string }) {
  if (!active) return null;
  return (
    <span data-testid="pulse-dot" aria-hidden="true" className={`inline-block h-1.5 w-1.5 animate-pulse rounded-full ${className}`} />
  );
}
