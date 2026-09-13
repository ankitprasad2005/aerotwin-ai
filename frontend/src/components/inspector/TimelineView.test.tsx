import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/mswServer";
import { TimelineView } from "./TimelineView";

function renderTimeline(agentExecutionId: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TimelineView agentExecutionId={agentExecutionId} />
    </QueryClientProvider>,
  );
}

describe("TimelineView", () => {
  it("shows an empty state when there are no events", async () => {
    server.use(http.get("http://localhost:8000/api/events", () => HttpResponse.json([])));
    renderTimeline("1");
    await waitFor(() => expect(screen.getByText("[NO TIMELINE EVENTS]")).toBeInTheDocument());
  });

  it("renders events in chronological order (oldest first), reversing the backend's newest-first order", async () => {
    server.use(
      http.get("http://localhost:8000/api/events", () =>
        HttpResponse.json([
          {
            id: "2",
            run_id: "r1",
            agent_execution_id: "1",
            event_type: "agent.completed",
            severity: "INFO",
            entity_type: null,
            entity_id: null,
            payload: {},
            created_at: "2026-09-11T09:42:40Z",
          },
          {
            id: "1",
            run_id: "r1",
            agent_execution_id: "1",
            event_type: "agent.started",
            severity: "INFO",
            entity_type: null,
            entity_id: null,
            payload: {},
            created_at: "2026-09-11T09:42:31Z",
          },
        ]),
      ),
    );
    renderTimeline("1");
    await waitFor(() => expect(screen.getByTestId("timeline-view")).toBeInTheDocument());
    const items = screen.getByTestId("timeline-view").querySelectorAll("li");
    expect(items[0]).toHaveTextContent("Task created");
    expect(items[1]).toHaveTextContent("Agent completed.");
  });
});
