import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { useConnectionStore } from "../../stores/connectionStore";
import { useDebugStore } from "../../stores/debugStore";
import { useEventStreamStore } from "../../stores/eventStreamStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import type { EventRecord } from "../../types";
import { ActivityFeed } from "./ActivityFeed";

function event(patch: Partial<EventRecord> = {}): EventRecord {
  return {
    id: "1",
    run_id: "r1",
    agent_execution_id: null,
    event_type: "orchestration.started",
    severity: "INFO",
    entity_type: null,
    entity_id: null,
    payload: { objective: "x" },
    created_at: "2026-10-15T10:00:00Z",
    ...patch,
  };
}

beforeEach(() => {
  useEventStreamStore.getState().clear();
  useInspectorStore.getState().close();
  useDebugStore.setState({ enabled: false });
  useConnectionStore.setState({ status: "open" });
});

describe("ActivityFeed", () => {
  it("tells the user it is waiting when connected with no events", () => {
    render(<ActivityFeed />);
    expect(screen.getByText("Waiting for events")).toBeInTheDocument();
  });

  it("says the feed is disconnected when the WebSocket is down", () => {
    useConnectionStore.setState({ status: "closed" });
    render(<ActivityFeed />);
    expect(screen.getByText("Live feed is not connected")).toBeInTheDocument();
    expect(screen.getByText(/keeps retrying/)).toBeInTheDocument();
  });

  it("lists events newest first with a source label and message", () => {
    useEventStreamStore.getState().addEvent(event({ id: "1", event_type: "orchestration.started" }));
    useEventStreamStore.getState().addEvent(event({ id: "2", event_type: "orchestration.completed", severity: "WARN" }));
    render(<ActivityFeed />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Orchestration completed.");
    expect(items[1]).toHaveTextContent("New optimization objective received.");
    expect(screen.getAllByText("ORCHESTRATOR")).toHaveLength(2);
    expect(screen.getByTestId("activity-feed")).toBeInTheDocument();
  });

  it("opens the inspector for events that belong to an agent only", async () => {
    useEventStreamStore.getState().addEvent(event({ id: "1" }));
    useEventStreamStore.getState().addEvent(event({ id: "2", agent_execution_id: "a1", event_type: "agent.completed", severity: "ERROR" }));
    render(<ActivityFeed />);
    expect(screen.getAllByRole("button")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button"));
    expect(useInspectorStore.getState().agentExecutionId).toBe("a1");
  });

  it("shows payloads only in debug mode", () => {
    useEventStreamStore.getState().addEvent(event({ payload: { secret: "visible-in-debug" } }));
    const { rerender } = render(<ActivityFeed />);
    expect(screen.queryByText(/visible-in-debug/)).not.toBeInTheDocument();
    useDebugStore.setState({ enabled: true });
    rerender(<ActivityFeed />);
    expect(screen.getByText(/visible-in-debug/)).toBeInTheDocument();
  });

  it("limits how many rows are rendered", () => {
    for (let i = 0; i < 10; i += 1) useEventStreamStore.getState().addEvent(event({ id: String(i) }));
    render(<ActivityFeed limit={3} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("falls back to a neutral dot for an unknown severity", () => {
    useEventStreamStore.getState().addEvent(event({ severity: "WEIRD" as never }));
    const { container } = render(<ActivityFeed />);
    expect(container.querySelector(".bg-faint")).not.toBeNull();
  });
});
