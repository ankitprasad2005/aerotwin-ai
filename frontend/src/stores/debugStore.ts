import { create } from "zustand";

interface DebugState {
  enabled: boolean;
  toggle: () => void;
}

export const useDebugStore = create<DebugState>((set) => ({
  enabled: false,
  toggle: () => set((state) => ({ enabled: !state.enabled })),
}));
