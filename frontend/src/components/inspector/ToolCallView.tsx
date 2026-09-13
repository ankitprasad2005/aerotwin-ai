import { useDebugStore } from "../../stores/debugStore";
import type { ToolExecution } from "../../types";

export function ToolCallView({ toolExecutions }: { toolExecutions: ToolExecution[] }) {
  const debugEnabled = useDebugStore((state) => state.enabled);

  if (toolExecutions.length === 0) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
        [NO TOOL CALLS YET]
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-md" data-testid="tool-call-view">
      {toolExecutions.map((tool) => (
        <div key={tool.id} className="border border-border p-sm">
          <div className="font-mono text-body-sm text-text-primary">{tool.tool_name}</div>
          <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
            {tool.duration_ms}ms · {tool.data_source}
          </div>
          {tool.error ? (
            <div className="mt-xs font-mono text-body-sm text-accent">[ERROR: {tool.error}]</div>
          ) : (
            <pre className="mt-xs overflow-x-auto font-mono text-body-sm text-text-primary">
              {JSON.stringify(tool.result, null, 2)}
            </pre>
          )}
          {debugEnabled && (
            <details className="mt-xs border border-border p-sm">
              <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
                Arguments (debug)
              </summary>
              <pre className="mt-sm overflow-x-auto font-mono text-body-sm text-text-primary">
                {JSON.stringify(tool.arguments, null, 2)}
              </pre>
            </details>
          )}
        </div>
      ))}
    </div>
  );
}
