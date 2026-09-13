import { create } from "zustand";
import { useInspectorStore } from "./inspectorStore";

// See the matching comment in inspectorStore.ts — this and that file import each
// other, which is safe because both cross-references live inside open() closures
// invoked later, never at module-evaluation time.
interface DecisionInspectorState {
  decisionId: string | null;
  open: (decisionId: string) => void;
  close: () => void;
}

export const useDecisionInspectorStore = create<DecisionInspectorState>((set) => ({
  decisionId: null,
  // Mutually exclusive with the agent inspector — both render as full-height,
  // right-side slide-overs, so only one may be open at a time.
  open: (decisionId) => {
    useInspectorStore.getState().close();
    set({ decisionId });
  },
  close: () => set({ decisionId: null }),
}));
