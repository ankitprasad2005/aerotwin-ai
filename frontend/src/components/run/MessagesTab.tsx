import { useRunMessages } from "../../api/useRuns";
import { formatEventTimestamp } from "../../utils/formatEvent";
import { agentLabel } from "../../utils/recommendation";
import { Chip } from "../ui/Badge";
import { EmptyState, ErrorState, LoadingState } from "../ui/States";

function who(name: string): string {
  // Senders and receivers are agent types ("NETWORK"), the orchestrator, or the decision engine.
  return /^[A-Z_]+$/.test(name) ? agentLabel(name) : name;
}

/** The messages the orchestrator and agents passed to each other during the run. */
export function MessagesTab({ runId }: { runId: string }) {
  const { data: messages, isLoading, isError, error, refetch } = useRunMessages(runId);

  if (isLoading) return <LoadingState label="Loading messages…" />;
  if (isError) return <ErrorState title="Could not load messages" error={error} onRetry={() => void refetch()} />;
  if (!messages || messages.length === 0) {
    return (
      <EmptyState
        title="No messages were exchanged"
        hint="Agents send each other messages while they work, for example the network agent's choice of route. They appear here."
      />
    );
  }

  return (
    <div className="overflow-x-auto" data-testid="messages-tab">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-line">
            <th className="th">Time</th>
            <th className="th">From</th>
            <th className="th">To</th>
            <th className="th">Type</th>
            <th className="th">Payload</th>
          </tr>
        </thead>
        <tbody>
          {messages.map((message) => (
            <tr key={message.id} className="border-b border-line align-top last:border-0">
              <td className="td whitespace-nowrap font-mono text-muted">{formatEventTimestamp(message.created_at)}</td>
              <td className="td">{who(message.sender)}</td>
              <td className="td">{who(message.receiver)}</td>
              <td className="td">
                <Chip>{message.message_type}</Chip>
              </td>
              <td className="td">
                <details>
                  <summary className="cursor-pointer text-xs text-accent">
                    {Object.keys(message.payload).length} field{Object.keys(message.payload).length === 1 ? "" : "s"}
                  </summary>
                  <pre className="mt-1 max-w-[520px] overflow-x-auto whitespace-pre-wrap break-words font-mono text-xs text-ink">
                    {JSON.stringify(message.payload, null, 2)}
                  </pre>
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
