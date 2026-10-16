import type { ContextSnapshot } from "../../types";

export function ContextTab({ contextSnapshot }: { contextSnapshot: ContextSnapshot | null }) {
  if (!contextSnapshot) {
    return (
      <div className="label text-faint">
        [NO CONTEXT SNAPSHOT]
      </div>
    );
  }

  const routing = contextSnapshot.evidence_routing ?? [];
  const topics = [...new Set(routing.map((r) => r.topic))];

  return (
    <div className="flex flex-col gap-sm" data-testid="context-tab">
      {routing.length > 0 && (
        <p className="text-xs text-muted" data-testid="evidence-routing">
          Added because the objective mentions: {topics.join(", ")}
        </p>
      )}
      {Object.entries(contextSnapshot.payload).map(([key, value]) => (
        <details key={key} className="border border-line p-sm">
          <summary className="cursor-pointer label text-muted">
            {key}
          </summary>
          <pre className="mt-sm overflow-x-auto font-mono text-sm text-ink">
            {JSON.stringify(value, null, 2)}
          </pre>
        </details>
      ))}
    </div>
  );
}
