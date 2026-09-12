import { create } from "zustand";

export type ConnectionStatus = "connecting" | "open" | "closed";

interface ConnectionState {
  status: ConnectionStatus;
  setStatus: (status: ConnectionStatus) => void;
}

export const useConnectionStore = create<ConnectionState>((set) => ({
  status: "connecting",
  setStatus: (status) => set({ status }),
}));
