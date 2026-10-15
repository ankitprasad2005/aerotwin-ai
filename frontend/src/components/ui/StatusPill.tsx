const STATUS_COLOR: Record<string, string> = {
  WAITING: "text-muted",
  QUEUED: "text-muted",
  RUNNING: "text-accent",
  WAITING_FOR_LLM: "text-accent",
  WAITING_FOR_TOOL: "text-accent",
  COMPLETED: "text-ok",
  SUCCESS: "text-ok",
  FAILED: "text-bad",
  RETRYING: "text-warn",
  BLOCKED: "text-warn",
  FALLBACK: "text-warn",
  RECOMMENDED: "text-ok",
  INFO: "text-muted",
  WARN: "text-warn",
  ERROR: "text-bad",
};

const LIVE_STATUSES = new Set(["RUNNING", "WAITING_FOR_LLM", "WAITING_FOR_TOOL"]);

export function StatusPill({ status }: { status: string }) {
  const colorClass = STATUS_COLOR[status] ?? "text-muted";
  const isLive = LIVE_STATUSES.has(status);

  return (
    <span className={`inline-flex items-center gap-1.5 font-mono text-xs uppercase tracking-wide ${colorClass}`}>
      {isLive && <span data-testid="status-pulse" className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {status}
    </span>
  );
}
