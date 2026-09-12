export function Pulse({ active }: { active: boolean }) {
  if (!active) return null;
  return <span data-testid="pulse-dot" className="inline-block h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />;
}
