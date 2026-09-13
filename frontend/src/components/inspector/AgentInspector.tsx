import { useEffect, useState } from "react";
import { useAgentExecutionDetail } from "../../api/useAgentExecutionDetail";
import { SlideOver } from "../layout/SlideOver";
import { ContextTab } from "./ContextTab";
import { LLMCallView } from "./LLMCallView";
import { OverviewTab } from "./OverviewTab";
import { TimelineView } from "./TimelineView";
import { ToolCallView } from "./ToolCallView";

type TabKey = "overview" | "context" | "timeline" | "llm" | "tools";

const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "OVERVIEW" },
  { key: "context", label: "CONTEXT" },
  { key: "timeline", label: "TIMELINE" },
  { key: "llm", label: "LLM CALL" },
  { key: "tools", label: "TOOL CALLS" },
];

export function AgentInspector({
  agentExecutionId,
  onClose,
}: {
  agentExecutionId: string | null;
  onClose: () => void;
}) {
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const { data: detail, isLoading, isError } = useAgentExecutionDetail(agentExecutionId ?? undefined);

  // AgentInspector is mounted once at the app root and reused across every open/close
  // (see the debug-mode wiring task) — without this, reopening for a different agent
  // execution would keep showing whatever tab was active when the previous one closed.
  useEffect(() => {
    setActiveTab("overview");
  }, [agentExecutionId]);

  return (
    <SlideOver open={agentExecutionId !== null} onClose={onClose}>
      <div className="flex flex-col gap-lg p-lg">
        <h2 className="font-display text-2xl text-text-display">AGENT INSPECTOR</h2>

        {isLoading && (
          <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">[LOADING...]</div>
        )}
        {isError && (
          <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-accent">
            [ERROR LOADING AGENT]
          </div>
        )}

        {detail && (
          <>
            <nav className="flex gap-md border-b border-border">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`pb-sm font-mono text-[11px] uppercase tracking-[0.08em] ${
                    activeTab === tab.key ? "border-b border-accent text-accent" : "text-text-secondary"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>

            {activeTab === "overview" && <OverviewTab detail={detail} />}
            {activeTab === "context" && <ContextTab contextSnapshot={detail.context_snapshot} />}
            {activeTab === "llm" && <LLMCallView llmExecution={detail.llm_execution} />}
            {activeTab === "tools" && <ToolCallView toolExecutions={detail.tool_executions} />}
            {activeTab === "timeline" && <TimelineView agentExecutionId={detail.id} />}
          </>
        )}
      </div>
    </SlideOver>
  );
}
