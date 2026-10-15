import { useEffect, useRef } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AgentInspector } from "./components/inspector/AgentInspector";
import { DecisionSummary } from "./components/inspector/DecisionSummary";
import { IconRail } from "./components/layout/IconRail";
import { KpiStrip } from "./components/layout/KpiStrip";
import { useEventStream } from "./hooks/useEventStream";
import { DataPage } from "./pages/DataPage";
import { EventsPage } from "./pages/EventsPage";
import { NewRunPage } from "./pages/NewRunPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RunPage } from "./pages/RunPage";
import { RunsPage } from "./pages/RunsPage";
import { WeightsPage } from "./pages/WeightsPage";
import { useDecisionInspectorStore } from "./stores/decisionInspectorStore";
import { useInspectorStore } from "./stores/inspectorStore";

export function App() {
  useEventStream();
  const location = useLocation();
  const inspectedAgentExecutionId = useInspectorStore((state) => state.agentExecutionId);
  const closeInspector = useInspectorStore((state) => state.close);
  const inspectedDecisionId = useDecisionInspectorStore((state) => state.decisionId);
  const closeDecision = useDecisionInspectorStore((state) => state.close);

  // Both inspectors are single global overlays, not scoped to any one page — close
  // them on navigation so neither lingers over unrelated content the user didn't ask
  // to inspect. Skip the very first run: an inspector opened before/during initial
  // mount (e.g. a deep link) shouldn't be closed by the mount itself, only by an
  // actual path change.
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    closeInspector();
    closeDecision();
  }, [location.pathname, closeInspector, closeDecision]);

  return (
    <div className="flex h-screen bg-canvas text-ink">
      <IconRail />
      <div className="flex min-w-0 flex-1 flex-col">
        <KpiStrip />
        <main className="flex-1 overflow-y-auto p-3 sm:p-4">
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/runs" element={<RunsPage />} />
            <Route path="/runs/:id" element={<RunPage />} />
            <Route path="/new" element={<NewRunPage />} />
            <Route path="/data" element={<DataPage />} />
            <Route path="/weights" element={<WeightsPage />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/orchestration" element={<Navigate to="/new" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
      <AgentInspector agentExecutionId={inspectedAgentExecutionId} onClose={closeInspector} />
      <DecisionSummary decisionId={inspectedDecisionId} onClose={closeDecision} />
    </div>
  );
}
