const STATUS_COLOR: Record<string, string> = {
  WAITING: "text-text-secondary",
  QUEUED: "text-text-secondary",
  RUNNING: "text-accent",
  WAITING_FOR_LLM: "text-accent",
  WAITING_FOR_TOOL: "text-accent",
  COMPLETED: "text-success",
  FAILED: "text-accent",
  RETRYING: "text-warning",
  BLOCKED: "text-warning",
  RECOMMENDED: "text-success",
  INFO: "text-text-secondary",
  WARN: "text-warning",
  ERROR: "text-accent",
};

const LIVE_STATUSES = new Set(["RUNNING", "WAITING_FOR_LLM", "WAITING_FOR_TOOL"]);

export function StatusPill({ status }: { status: string }) {
  const colorClass = STATUS_COLOR[status] ?? "text-text-secondary";
  const isLive = LIVE_STATUSES.has(status);

  return (
    <span className={`inline-flex items-center gap-xs font-mono text-[11px] uppercase tracking-[0.08em] ${colorClass}`}>
      {isLive && (
        <span data-testid="status-pulse" className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
      )}
      {status}
    </span>
  );
}
