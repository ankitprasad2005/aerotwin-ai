import type { ReactNode } from "react";
import { Button } from "./Button";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 py-3 text-sm text-muted">
      <span aria-hidden="true" className="h-3 w-3 animate-spin rounded-full border-2 border-line-strong border-t-accent" />
      {label}
    </div>
  );
}

/** An inline error with an optional retry. `error` is the thrown value; ApiError messages are
 * already human-readable (see api/client.ts). */
export function ErrorState({
  title = "Something went wrong",
  error,
  onRetry,
}: {
  title?: string;
  error?: unknown;
  onRetry?: () => void;
}) {
  const detail = error instanceof Error && error.message ? error.message : null;
  return (
    <div role="alert" className="rounded-sm border border-bad/40 bg-bad/5 px-3 py-2 text-sm">
      <div className="font-medium text-bad">{title}</div>
      {detail && <div className="mt-0.5 break-words text-muted">{detail}</div>}
      {onRetry && (
        <Button variant="ghost" className="mt-2" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1 px-3 py-6 text-center">
      <div className="text-sm font-medium text-ink">{title}</div>
      {hint && <div className="max-w-md text-sm text-muted">{hint}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
