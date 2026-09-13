import { create } from "zustand";
import { useDecisionInspectorStore } from "./decisionInspectorStore";

interface InspectorState {
  agentExecutionId: string | null;
  open: (agentExecutionId: string) => void;
  close: () => void;
}

export const useInspectorStore = create<InspectorState>((set) => ({
  agentExecutionId: null,
  // Mutually exclusive with the decision inspector — both render as full-height,
  // right-side slide-overs, so only one may be open at a time.
  open: (agentExecutionId) => {
    useDecisionInspectorStore.getState().close();
    set({ agentExecutionId });
  },
  close: () => set({ agentExecutionId: null }),
}));
