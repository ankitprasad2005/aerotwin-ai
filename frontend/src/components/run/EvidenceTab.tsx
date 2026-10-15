import { useMemo } from "react";
import { useRunEvidence } from "../../api/useRuns";
import type { RunEvidenceEntry } from "../../types/api";
import { contentPreview, groupEvidence, inIteration, safeHref, unknownCitations } from "../../utils/evidence";
import { formatDateTime } from "../../utils/format";
import { agentLabel } from "../../utils/recommendation";
import { Chip, ReliabilityBar } from "../ui/Badge";
import { EmptyState, ErrorState, LoadingState } from "../ui/States";
import { Panel } from "../ui/Panel";

/** The external evidence the agents were given, grouped by source: how reliable it is, who saw it,
 * who cited it, and which providers had nothing to offer. Web results are untrusted text, so their
 * titles and snippets are rendered as plain text and links are limited to http(s). */
export function EvidenceList({ entries }: { entries: RunEvidenceEntry[] }) {
  const groups = useMemo(() => groupEvidence(entries), [entries]);
  const unavailable = useMemo(
    () => [...new Set(entries.flatMap((entry) => entry.evidence_unavailable))],
    [entries],
  );
  const ghosts = useMemo(() => unknownCitations(entries), [entries]);

  if (groups.length === 0 && unavailable.length === 0) {
    return (
      <EmptyState
        title="No external evidence was gathered for this prompt"
        hint="Agents then relied on the digital twin alone. Refresh the datasets on the Data page to give them market, fuel and traffic evidence."
      />
    );
  }

  return (
    <div className="space-y-3" data-testid="evidence-list">
      {groups.map((group) => (
        <Panel key={group.source} title={`${group.label} (${group.items.length})`} padded={false} data-testid={`evidence-group-${group.source}`}>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-line">
                  <th className="th">Item</th>
                  <th className="th">Reliability</th>
                  <th className="th">Fetched</th>
                  <th className="th">Seen by</th>
                  <th className="th">Cited by</th>
                </tr>
              </thead>
              <tbody>
                {group.items.map(({ item, seenBy, citedBy }) => {
                  const href = safeHref(item.url);
                  return (
                    <tr key={item.id} className="border-b border-line align-top last:border-0">
                      <td className="td max-w-[420px]">
                        {href ? (
                          <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="break-words font-medium text-accent hover:underline">
                            {item.title}
                          </a>
                        ) : (
                          <span className="break-words font-medium text-ink-strong">{item.title}</span>
                        )}
                        <div className="mt-0.5 break-words text-xs text-muted">{contentPreview(item.content)}</div>
                        <div className="mt-0.5 font-mono text-2xs text-faint">{item.id}</div>
                      </td>
                      <td className="td">
                        <ReliabilityBar value={item.reliability} />
                      </td>
                      <td className="td whitespace-nowrap text-muted">{formatDateTime(item.fetched_at)}</td>
                      <td className="td">
                        <span className="flex flex-wrap gap-1">
                          {seenBy.map((agent) => (
                            <Chip key={agent}>{agentLabel(agent)}</Chip>
                          ))}
                        </span>
                      </td>
                      <td className="td">
                        {citedBy.length === 0 ? (
                          <span className="text-muted">not cited</span>
                        ) : (
                          <span className="flex flex-wrap gap-1">
                            {citedBy.map((agent) => (
                              <Chip key={agent} tone="accent">
                                {agentLabel(agent)}
                              </Chip>
                            ))}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      ))}

      {unavailable.length > 0 && (
        <div className="rounded-sm border border-warn/40 bg-warn/5 px-3 py-2 text-sm" data-testid="evidence-unavailable">
          <div className="label text-warn">Providers without data ({unavailable.length})</div>
          <ul className="mt-1 list-disc pl-4 text-ink">
            {unavailable.map((reason) => (
              <li key={reason} className="break-words">
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {ghosts.length > 0 && (
        <div className="rounded-sm border border-bad/40 bg-bad/5 px-3 py-2 text-sm" data-testid="evidence-unknown-citations">
          <div className="label text-bad">Citations that match no evidence ({ghosts.length})</div>
          <p className="mt-1 text-muted">An agent cited ids it was never given. Treat those claims with care.</p>
          <span className="mt-1 flex flex-wrap gap-1">
            {ghosts.map((id) => (
              <Chip key={id} tone="bad">
                {id}
              </Chip>
            ))}
          </span>
        </div>
      )}
    </div>
  );
}

/** Fetches the run's evidence and shows the part belonging to one prompt (iteration). */
export function EvidenceTab({ runId, iteration }: { runId: string; iteration: number }) {
  const { data, isLoading, isError, error, refetch } = useRunEvidence(runId);
  const entries = useMemo(() => (data ?? []).filter((entry) => inIteration(entry, iteration)), [data, iteration]);

  if (isLoading) return <LoadingState label="Loading evidence…" />;
  if (isError) return <ErrorState title="Could not load evidence" error={error} onRetry={() => void refetch()} />;
  return <EvidenceList entries={entries} />;
}
