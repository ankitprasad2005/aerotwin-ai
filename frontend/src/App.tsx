import { useEffect, useRef } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { AgentInspector } from "./components/inspector/AgentInspector";
import { HeaderBar } from "./components/layout/HeaderBar";
import { Sidebar } from "./components/layout/Sidebar";
import { useEventStream } from "./hooks/useEventStream";
import { DashboardPage } from "./pages/DashboardPage";
import { EventsPage } from "./pages/EventsPage";
import { OrchestrationPage } from "./pages/OrchestrationPage";
import { useDebugStore } from "./stores/debugStore";
import { useInspectorStore } from "./stores/inspectorStore";

export function App() {
  useEventStream();
  const navigate = useNavigate();
  const location = useLocation();
  const debugEnabled = useDebugStore((state) => state.enabled);
  const toggleDebug = useDebugStore((state) => state.toggle);
  const inspectedAgentExecutionId = useInspectorStore((state) => state.agentExecutionId);
  const closeInspector = useInspectorStore((state) => state.close);

  // The inspector is a single global overlay, not scoped to any one page — close it on
  // navigation so it never lingers over unrelated content the user didn't ask to inspect.
  // Skip the very first run: an inspector opened before/during initial mount (e.g. a
  // deep link) shouldn't be closed by the mount itself, only by an actual path change.
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    closeInspector();
  }, [location.pathname, closeInspector]);

  return (
    <div className="flex h-screen bg-black text-text-primary font-body">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <HeaderBar debugMode={debugEnabled} onToggleDebug={toggleDebug} onNewRun={() => navigate("/orchestration")} />
        <main className="flex-1 overflow-y-auto p-lg">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/orchestration" element={<OrchestrationPage />} />
            <Route path="/events" element={<EventsPage />} />
          </Routes>
        </main>
      </div>
      <AgentInspector agentExecutionId={inspectedAgentExecutionId} onClose={closeInspector} />
    </div>
  );
}
