import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { useDebugStore } from "../../stores/debugStore";
import { useEventStreamStore } from "../../stores/eventStreamStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import { ActivityFeed } from "./ActivityFeed";

beforeEach(() => {
  useEventStreamStore.getState().clear();
});

describe("ActivityFeed", () => {
  it("shows a placeholder when there are no events", () => {
    render(<ActivityFeed />);
    expect(screen.getByText("[NO EVENTS YET]")).toBeInTheDocument();
  });

  it("renders one line per event, newest first", () => {
    useEventStreamStore.getState().addEvent({
      id: "1",
      run_id: "r1",
      agent_execution_id: null,
      event_type: "orchestration.started",
      severity: "INFO",
      entity_type: null,
      entity_id: null,
      payload: {},
      created_at: "2026-09-11T09:42:31Z",
    });
    useEventStreamStore.getState().addEvent({
      id: "2",
      run_id: "r1",
      agent_execution_id: null,
      event_type: "orchestration.completed",
      severity: "INFO",
      entity_type: null,
      entity_id: null,
      payload: {},
      created_at: "2026-09-11T09:42:40Z",
    });

    render(<ActivityFeed />);
    const items = screen.getByTestId("activity-feed").querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Orchestration completed.");
    expect(items[1]).toHaveTextContent("New optimization objective received.");
  });

  it("opens the inspector when a line with an agent_execution_id is clicked", async () => {
    useEventStreamStore.getState().addEvent({
      id: "1",
      run_id: "r1",
      agent_execution_id: "a1",
      event_type: "agent.started",
      severity: "INFO",
      entity_type: null,
      entity_id: null,
      payload: {},
      created_at: "2026-09-11T09:42:31Z",
    });
    render(<ActivityFeed />);
    await userEvent.click(screen.getByRole("button"));
    expect(useInspectorStore.getState().agentExecutionId).toBe("a1");
  });

  it("does not render a clickable button for lines with no agent_execution_id", () => {
    useEventStreamStore.getState().addEvent({
      id: "1",
      run_id: "r1",
      agent_execution_id: null,
      event_type: "orchestration.started",
      severity: "INFO",
      entity_type: null,
      entity_id: null,
      payload: {},
      created_at: "2026-09-11T09:42:31Z",
    });
    render(<ActivityFeed />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows the raw payload when debug mode is enabled", () => {
    useDebugStore.setState({ enabled: true });
    useEventStreamStore.getState().addEvent({
      id: "1",
      run_id: "r1",
      agent_execution_id: null,
      event_type: "orchestration.started",
      severity: "INFO",
      entity_type: null,
      entity_id: null,
      payload: { objective: "x" },
      created_at: "2026-09-11T09:42:31Z",
    });
    render(<ActivityFeed />);
    expect(screen.getByText(/"objective": "x"/)).toBeInTheDocument();
    useDebugStore.setState({ enabled: false });
  });
});
