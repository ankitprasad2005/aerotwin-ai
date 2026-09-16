import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useRuns } from "../api/useRuns";
import { ExecutionGraph } from "../components/orchestration/ExecutionGraph";
import { KnowledgeGraph } from "../components/orchestration/KnowledgeGraph";
import { ObjectiveForm } from "../components/orchestration/ObjectiveForm";
import { PromptPanel } from "../components/orchestration/PromptPanel";
import { RunList } from "../components/orchestration/RunList";
import { RunOutput } from "../components/orchestration/RunOutput";
import { StatusPill } from "../components/ui/StatusPill";

type TabKey = "output" | "execution" | "knowledge" | "prompt";

const TABS: { key: TabKey; label: string }[] = [
  { key: "output", label: "OUTPUT" },
  { key: "execution", label: "EXECUTION GRAPH" },
  { key: "knowledge", label: "KNOWLEDGE GRAPH" },
  { key: "prompt", label: "PROMPT" },
];

export function OrchestrationPage() {
  const [searchParams] = useSearchParams();
  // Deep-link support for RecentRunsList's row click (/orchestration?run=<id>). The run list
  // doesn't write back to the URL as the user picks runs, since nothing else needs to observe that
  // selection — but the selection does follow later changes to ?run=: this page stays mounted
  // across same-route navigations (browser back/forward between run links).
  const runParam = searchParams.get("run");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(runParam);
  const [activeTab, setActiveTab] = useState<TabKey>("output");
  useEffect(() => {
    setSelectedRunId(runParam);
  }, [runParam]);
  const { data: runs } = useRuns();
  const selectedRun = (runs ?? []).find((run) => run.id === selectedRunId);

  function selectRun(runId: string) {
    setSelectedRunId(runId);
    setActiveTab("output");
  }

  return (
    <div data-testid="page-content" className="flex flex-col gap-lg">
      <h1 className="font-display text-3xl text-text-display">ORCHESTRATION</h1>
      <ObjectiveForm onRunCreated={selectRun} />

      <div className="flex gap-lg">
        <aside className="flex w-72 shrink-0 flex-col border-r border-border pr-md">
          <h2 className="mb-sm font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">All runs</h2>
          <div className="max-h-[640px] overflow-y-auto">
            <RunList selectedRunId={selectedRunId} onSelect={selectRun} />
          </div>
        </aside>

        <section className="min-w-0 flex-1">
          {selectedRunId ? (
            <div className="flex flex-col gap-md">
              <div className="flex items-start justify-between gap-sm">
                <div>
                  <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary">Run</div>
                  <p className="text-body text-text-display">{selectedRun?.objective ?? selectedRunId}</p>
                </div>
                {selectedRun && <StatusPill status={selectedRun.status} />}
              </div>

              <nav className="flex gap-md border-b border-border" role="tablist">
                {TABS.map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === tab.key}
                    onClick={() => setActiveTab(tab.key)}
                    className={`pb-sm font-mono text-[11px] uppercase tracking-[0.08em] ${
                      activeTab === tab.key ? "border-b border-accent text-accent" : "text-text-secondary"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </nav>

              {activeTab === "output" && <RunOutput runId={selectedRunId} />}
              {activeTab === "execution" && <ExecutionGraph runId={selectedRunId} />}
              {activeTab === "knowledge" && <KnowledgeGraph runId={selectedRunId} />}
              {activeTab === "prompt" && <PromptPanel runId={selectedRunId} />}
            </div>
          ) : (
            <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
              [SELECT OR START A RUN TO VIEW ITS EXECUTION GRAPH]
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
