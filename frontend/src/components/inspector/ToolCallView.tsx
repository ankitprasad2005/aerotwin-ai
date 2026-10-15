import { useDebugStore } from "../../stores/debugStore";
import type { ToolExecution } from "../../types";

export function ToolCallView({ toolExecutions }: { toolExecutions: ToolExecution[] }) {
  const debugEnabled = useDebugStore((state) => state.enabled);

  if (toolExecutions.length === 0) {
    return (
      <div className="label text-faint">
        [NO TOOL CALLS YET]
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-md" data-testid="tool-call-view">
      {toolExecutions.map((tool) => (
        <div key={tool.id} className="border border-line p-sm">
          <div className="font-mono text-sm text-ink">{tool.tool_name}</div>
          <div className="label text-muted">
            {tool.duration_ms}ms · {tool.data_source}
          </div>
          {tool.error ? (
            <div className="mt-xs font-mono text-sm text-bad">[ERROR: {tool.error}]</div>
          ) : (
            <pre className="mt-xs overflow-x-auto font-mono text-sm text-ink">
              {JSON.stringify(tool.result, null, 2)}
            </pre>
          )}
          {debugEnabled && (
            <details className="mt-xs border border-line p-sm">
              <summary className="cursor-pointer label text-muted">
                Arguments (debug)
              </summary>
              <pre className="mt-sm overflow-x-auto font-mono text-sm text-ink">
                {JSON.stringify(tool.arguments, null, 2)}
              </pre>
            </details>
          )}
        </div>
      ))}
    </div>
  );
}
