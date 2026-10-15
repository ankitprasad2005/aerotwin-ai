import { useDebugStore } from "../../stores/debugStore";
import type { LLMExecution } from "../../types";

export function LLMCallView({ llmExecution }: { llmExecution: LLMExecution | null }) {
  const debugEnabled = useDebugStore((state) => state.enabled);

  if (!llmExecution) {
    return (
      <div className="label text-faint">[NO LLM CALL YET]</div>
    );
  }

  return (
    <div className="flex flex-col gap-md" data-testid="llm-call-view">
      <dl className="grid grid-cols-2 gap-sm">
        <dt className="label text-muted">Provider</dt>
        <dd className="text-sm text-ink">{llmExecution.provider}</dd>

        <dt className="label text-muted">Model</dt>
        <dd className="text-sm text-ink">{llmExecution.model}</dd>

        <dt className="label text-muted">Duration</dt>
        <dd className="font-mono text-sm text-ink">
          {(llmExecution.duration_ms / 1000).toFixed(1)}s
        </dd>

        <dt className="label text-muted">Tokens</dt>
        <dd className="font-mono text-sm text-ink">
          {llmExecution.input_tokens} in / {llmExecution.output_tokens} out / {llmExecution.total_tokens} total
        </dd>

        <dt className="label text-muted">Retries</dt>
        <dd className="font-mono text-sm text-ink">{llmExecution.retry_count}</dd>

        <dt className="label text-muted">Status</dt>
        <dd className="text-sm text-ink">{llmExecution.status}</dd>
      </dl>

      <details className="border border-line p-sm">
        <summary className="cursor-pointer label text-muted">
          System instructions
        </summary>
        <pre className="mt-sm overflow-x-auto whitespace-pre-wrap font-mono text-sm text-ink">
          {llmExecution.system_instructions}
        </pre>
      </details>

      <details className="border border-line p-sm">
        <summary className="cursor-pointer label text-muted">
          Context sent to model
        </summary>
        <pre className="mt-sm overflow-x-auto font-mono text-sm text-ink">
          {JSON.stringify(llmExecution.context, null, 2)}
        </pre>
      </details>

      <details className="border border-line p-sm">
        <summary className="cursor-pointer label text-muted">
          Available tools
        </summary>
        <pre className="mt-sm overflow-x-auto font-mono text-sm text-ink">
          {JSON.stringify(llmExecution.available_tools, null, 2)}
        </pre>
      </details>

      {debugEnabled && (
        <details className="border border-line p-sm">
          <summary className="cursor-pointer label text-muted">
            Raw response (debug)
          </summary>
          <pre className="mt-sm overflow-x-auto font-mono text-sm text-ink">
            {JSON.stringify(llmExecution.raw_response, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
