import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { useConnectionStore } from "../stores/connectionStore";
import { useEventStreamStore } from "../stores/eventStreamStore";
import { api, makeStats, makeStatsRun } from "../test/fixtures";
import { server } from "../test/mswServer";
import { renderWithProviders } from "../test/render";
import { OverviewPage } from "./OverviewPage";

beforeEach(() => {
  useEventStreamStore.getState().clear();
  useConnectionStore.setState({ status: "open" });
});

function mock(stats = makeStats(), runs = [makeStatsRun()]) {
  server.use(
    http.get(api("/api/stats"), () => HttpResponse.json(stats)),
    http.get(api("/api/stats/runs"), () => HttpResponse.json(runs)),
  );
}

describe("OverviewPage", () => {
  it("shows tiles, the verdict split and recent decisions", async () => {
    mock();
    renderWithProviders(<OverviewPage />);
    expect(screen.getByText("Loading statistics…")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("tile-Runs per day")).toHaveTextContent("3"));
    expect(screen.getByTestId("tile-Runs per day")).toHaveTextContent("12 runs in total");
    expect(screen.getByTestId("tile-Tokens per day")).toHaveTextContent("12.0K");
    expect(screen.getByTestId("tile-Tokens per day")).toHaveTextContent("250.0K tokens in total");
    expect(screen.getByTestId("tile-In flight")).toHaveTextContent("1");
    expect(screen.getByTestId("tile-In flight")).toHaveTextContent("9 completed");
    expect(screen.getByTestId("tile-Failed")).toHaveTextContent("Open the Runs page");
    expect(screen.getByRole("img", { name: /Decisions by verdict: Recommend 5, Review 3, Reject 1/ })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Improve airline profitability" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All runs" })).toHaveAttribute("href", "/runs");
  });

  it("copes with a brand-new database: no runs, no decisions, no series", async () => {
    mock(
      makeStats({
        runs_total: 0, runs_completed: 0, runs_failed: 0, runs_running: 0, tokens_total: 0, tokens_last_24h: 0,
        p95_run_duration_ms: null, runs_per_day: [], tokens_per_day: [],
        decisions_by_verdict: { RECOMMEND: 0, REVIEW: 0, REJECT: 0 },
      }),
      [],
    );
    renderWithProviders(<OverviewPage />);
    expect(await screen.findByTestId("verdicts-empty")).toBeInTheDocument();
    expect(screen.getByTestId("tile-Runs per day")).toHaveTextContent("0");
    expect(screen.getByTestId("tile-Failed")).toHaveTextContent("No failures");
    expect(await screen.findByText("No runs yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New run" })).toHaveAttribute("href", "/new");
  });

  it("shows errors for stats and runs independently, each with retry", async () => {
    let statsCalls = 0;
    server.use(
      http.get(api("/api/stats"), () => {
        statsCalls += 1;
        return statsCalls === 1 ? HttpResponse.json({ detail: "stats down" }, { status: 500 }) : HttpResponse.json(makeStats());
      }),
      http.get(api("/api/stats/runs"), () => HttpResponse.json({ detail: "runs down" }, { status: 500 })),
    );
    renderWithProviders(<OverviewPage />);
    expect(await screen.findByText("Could not load statistics")).toBeInTheDocument();
    expect(await screen.findByText("Could not load runs")).toBeInTheDocument();
    expect(screen.getAllByRole("alert")).toHaveLength(2);
    await userEvent.click(screen.getAllByRole("button", { name: "Try again" })[0]);
    await waitFor(() => expect(screen.getByTestId("tile-Failed")).toBeInTheDocument());
  });

  it("shows the live feed and updates it as events arrive", async () => {
    mock();
    renderWithProviders(<OverviewPage />);
    expect(await screen.findByText("Waiting for events")).toBeInTheDocument();
    act(() =>
      useEventStreamStore.getState().addEvent({
        id: "e1", run_id: "r1", agent_execution_id: null, event_type: "orchestration.started", severity: "INFO",
        entity_type: null, entity_id: null, payload: {}, created_at: "2026-10-15T10:00:00Z",
      }),
    );
    expect(screen.getByTestId("activity-feed")).toHaveTextContent("ORCHESTRATOR");
  });

  it("says the live feed is disconnected when the WebSocket is down", async () => {
    mock();
    useConnectionStore.setState({ status: "closed" });
    renderWithProviders(<OverviewPage />);
    expect(await screen.findByText("Live feed is not connected")).toBeInTheDocument();
  });
});
