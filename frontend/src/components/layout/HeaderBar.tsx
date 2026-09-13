import { Pulse } from "../ui/Pulse";
import { useConnectionStore } from "../../stores/connectionStore";
import { useDebugStore } from "../../stores/debugStore";

export function HeaderBar({ onNewRun }: { onNewRun: () => void }) {
  const status = useConnectionStore((state) => state.status);
  const debugMode = useDebugStore((state) => state.enabled);
  const toggleDebug = useDebugStore((state) => state.toggle);
  const statusColor = status === "open" ? "text-success" : status === "connecting" ? "text-warning" : "text-accent";
  const statusLabel = status === "open" ? "LIVE" : status === "connecting" ? "CONNECTING" : "DISCONNECTED";

  return (
    <header className="flex items-center justify-between border-b border-border bg-black px-lg py-sm">
      <div className={`flex items-center gap-xs font-mono text-[11px] uppercase tracking-[0.08em] ${statusColor}`}>
        <Pulse active={status === "open"} />
        {statusLabel}
      </div>
      <div className="flex items-center gap-md">
        <button
          onClick={toggleDebug}
          className={`font-mono text-[11px] uppercase tracking-[0.08em] ${
            debugMode ? "text-accent" : "text-text-secondary"
          }`}
        >
          DEBUG {debugMode ? "ON" : "OFF"}
        </button>
        <button
          onClick={onNewRun}
          className="bg-accent px-md py-sm font-mono text-[11px] uppercase tracking-[0.08em] text-text-display"
        >
          + NEW RUN
        </button>
      </div>
    </header>
  );
}
