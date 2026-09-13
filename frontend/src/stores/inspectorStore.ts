import { create } from "zustand";

interface InspectorState {
  agentExecutionId: string | null;
  open: (agentExecutionId: string) => void;
  close: () => void;
}

export const useInspectorStore = create<InspectorState>((set) => ({
  agentExecutionId: null,
  open: (agentExecutionId) => set({ agentExecutionId }),
  close: () => set({ agentExecutionId: null }),
}));
