import { Route, Routes, useNavigate } from "react-router-dom";
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
  const debugEnabled = useDebugStore((state) => state.enabled);
  const toggleDebug = useDebugStore((state) => state.toggle);
  const inspectedAgentExecutionId = useInspectorStore((state) => state.agentExecutionId);
  const closeInspector = useInspectorStore((state) => state.close);

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
