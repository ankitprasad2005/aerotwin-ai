import { create } from "zustand";
import { useDecisionInspectorStore } from "./decisionInspectorStore";

// This file and decisionInspectorStore.ts import each other. That's safe here — ESM
// evaluates each module's dependencies before its own body, so by the time either
// open() closure runs (only ever in response to a later user click, long after both
// modules have finished evaluating), both bindings are fully initialized. Neither
// store calls the other at module-evaluation time, only inside these action closures.
// Kept as two stores (rather than one `{kind, id}` union that would rule this out by
// construction) to leave inspectorStore's existing shape/call-sites untouched. If a
// third inspector type is ever added, switch to a unified store instead of a third
// pairwise cross-import.
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
