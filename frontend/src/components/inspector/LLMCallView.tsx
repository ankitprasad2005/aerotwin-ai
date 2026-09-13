import type { LLMExecution } from "../../types";

export function LLMCallView({ llmExecution }: { llmExecution: LLMExecution | null }) {
  if (!llmExecution) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[NO LLM CALL YET]</div>
    );
  }

  return (
    <div className="flex flex-col gap-md" data-testid="llm-call-view">
      <dl className="grid grid-cols-2 gap-sm">
        <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Provider</dt>
        <dd className="text-body-sm text-text-primary">{llmExecution.provider}</dd>

        <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Model</dt>
        <dd className="text-body-sm text-text-primary">{llmExecution.model}</dd>

        <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Duration</dt>
        <dd className="font-mono text-body-sm text-text-primary">
          {(llmExecution.duration_ms / 1000).toFixed(1)}s
        </dd>

        <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Tokens</dt>
        <dd className="font-mono text-body-sm text-text-primary">
          {llmExecution.input_tokens} in / {llmExecution.output_tokens} out / {llmExecution.total_tokens} total
        </dd>

        <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Retries</dt>
        <dd className="font-mono text-body-sm text-text-primary">{llmExecution.retry_count}</dd>

        <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Status</dt>
        <dd className="text-body-sm text-text-primary">{llmExecution.status}</dd>
      </dl>

      <details className="border border-border p-sm">
        <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
          System instructions
        </summary>
        <pre className="mt-sm overflow-x-auto whitespace-pre-wrap font-mono text-body-sm text-text-primary">
          {llmExecution.system_instructions}
        </pre>
      </details>

      <details className="border border-border p-sm">
        <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
          Context sent to model
        </summary>
        <pre className="mt-sm overflow-x-auto font-mono text-body-sm text-text-primary">
          {JSON.stringify(llmExecution.context, null, 2)}
        </pre>
      </details>

      <details className="border border-border p-sm">
        <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
          Available tools
        </summary>
        <pre className="mt-sm overflow-x-auto font-mono text-body-sm text-text-primary">
          {JSON.stringify(llmExecution.available_tools, null, 2)}
        </pre>
      </details>

      <details className="border border-border p-sm">
        <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">
          Raw response
        </summary>
        <pre className="mt-sm overflow-x-auto font-mono text-body-sm text-text-primary">
          {JSON.stringify(llmExecution.raw_response, null, 2)}
        </pre>
      </details>
    </div>
  );
}
