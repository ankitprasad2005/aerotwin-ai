import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useEventStreamStore } from "../../stores/eventStreamStore";
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
});
