import type { ContextSnapshot } from "../../types";

export function ContextTab({ contextSnapshot }: { contextSnapshot: ContextSnapshot | null }) {
  if (!contextSnapshot) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
        [NO CONTEXT SNAPSHOT]
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-sm" data-testid="context-tab">
      {Object.entries(contextSnapshot.payload).map(([key, value]) => (
        <details key={key} className="border border-border p-sm">
          <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
            {key}
          </summary>
          <pre className="mt-sm overflow-x-auto font-mono text-body-sm text-text-primary">
            {JSON.stringify(value, null, 2)}
          </pre>
        </details>
      ))}
    </div>
  );
}
