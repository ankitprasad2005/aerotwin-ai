import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useConnectionStore } from "../stores/connectionStore";
import { useEventStreamStore } from "../stores/eventStreamStore";
import { useEventStream } from "./useEventStream";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  url: string;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.closed = true;
    this.onclose?.();
  }
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
  vi.useFakeTimers();
  useConnectionStore.setState({ status: "connecting" });
  useEventStreamStore.getState().clear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useEventStream", () => {
  it("connects to the events WebSocket URL", () => {
    const { unmount } = renderHook(() => useEventStream());
    expect(FakeWebSocket.instances[0].url).toBe("ws://localhost:8000/ws/events");
    unmount();
  });

  it("sets connection status to open when the socket opens", () => {
    const { unmount } = renderHook(() => useEventStream());
    act(() => FakeWebSocket.instances[0].onopen?.());
    expect(useConnectionStore.getState().status).toBe("open");
    unmount();
  });

  it("parses incoming messages and adds them to the event store", () => {
    const { unmount } = renderHook(() => useEventStream());
    const socket = FakeWebSocket.instances[0];

    act(() => {
      socket.onmessage?.({
        data: JSON.stringify({
          id: "1",
          run_id: "r1",
          agent_execution_id: null,
          event_type: "agent.started",
          severity: "INFO",
          entity_type: null,
          entity_id: null,
          payload: {},
          created_at: "2026-09-11T00:00:00Z",
        }),
      });
    });

    expect(useEventStreamStore.getState().events).toHaveLength(1);
    expect(useEventStreamStore.getState().events[0].event_type).toBe("agent.started");
    unmount();
  });

  it("ignores a malformed message without throwing", () => {
    const { unmount } = renderHook(() => useEventStream());
    const socket = FakeWebSocket.instances[0];

    expect(() => act(() => socket.onmessage?.({ data: "not json" }))).not.toThrow();
    expect(useEventStreamStore.getState().events).toHaveLength(0);
    unmount();
  });

  it("sets status to closed and reconnects with backoff after a disconnect", () => {
    const { unmount } = renderHook(() => useEventStream());
    const firstSocket = FakeWebSocket.instances[0];

    act(() => firstSocket.onclose?.());
    expect(useConnectionStore.getState().status).toBe("closed");
    expect(FakeWebSocket.instances).toHaveLength(1);

    act(() => vi.advanceTimersByTime(1000));
    expect(FakeWebSocket.instances).toHaveLength(2);
    unmount();
  });

  it("does not reconnect after the component unmounts", () => {
    const { unmount } = renderHook(() => useEventStream());
    const firstSocket = FakeWebSocket.instances[0];
    unmount();

    act(() => firstSocket.onclose?.());
    act(() => vi.advanceTimersByTime(15000));

    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
