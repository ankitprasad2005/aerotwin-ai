import { useEffect } from "react";
import { useConnectionStore } from "../stores/connectionStore";
import { useEventStreamStore } from "../stores/eventStreamStore";
import type { EventRecord } from "../types";

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000";
const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 10000;

export function useEventStream() {
  const addEvent = useEventStreamStore((state) => state.addEvent);
  const setStatus = useConnectionStore((state) => state.setStatus);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let backoff = INITIAL_BACKOFF_MS;
    let stopped = false;

    function connect() {
      setStatus("connecting");
      socket = new WebSocket(`${WS_BASE_URL}/ws/events`);

      socket.onopen = () => {
        backoff = INITIAL_BACKOFF_MS;
        setStatus("open");
      };

      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data as string) as EventRecord;
          addEvent(event);
        } catch {
          // ignore malformed messages — a bad frame shouldn't take down the stream
        }
      };

      socket.onclose = () => {
        // Guard the whole body, not just the reconnect: WebSocket.close() is async, so a
        // stale socket's onclose can still fire after cleanup already ran (e.g. React
        // StrictMode's dev-only double-invoke) — without this, it would clobber
        // connectionStore.status back to "closed" after a newer socket already opened.
        if (stopped) return;
        setStatus("closed");
        reconnectTimer = setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
      };

      socket.onerror = () => {
        socket?.close();
      };
    }

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [addEvent, setStatus]);
}
