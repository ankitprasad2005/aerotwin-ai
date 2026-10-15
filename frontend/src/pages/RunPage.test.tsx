import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { runKeys } from "../api/useRuns";
import { useInspectorStore } from "../stores/inspectorStore";
import { api, defaultHandlers, makeAgent, makeDecision, makeIteration, makeRunDetail } from "../test/fixtures";
import { server } from "../test/mswServer";
import { renderWithProviders } from "../test/render";
import { RunPage } from "./RunPage";

const RUN_ID = "3f2a1b4c-5d6e-4f70-8a9b-0c1d2e3f4a5b";

beforeEach(() => {
  useInspectorStore.getState().close();
});

function renderRun(id = RUN_ID) {
  return renderWithProviders(<RunPage />, { route: `/runs/${id}`, path: "/runs/:id" });
}

function useRun(run = makeRunDetail({ id: RUN_ID })) {
  server.use(http.get(api("/api/runs/:id"), () => HttpResponse.json(run)), ...defaultHandlers());
}

describe("RunPage", () => {
  it("shows a loading state, then the decision, agents and tabs", async () => {
    useRun();
    renderRun();
    expect(screen.getByRole("status")).toHaveTextContent("Loading run");
    await waitFor(() => expect(screen.getByTestId("decision-panel")).toBeInTheDocument());
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Improve airline profitability");
    expect(screen.getByText("Recommend")).toBeInTheDocument();
    expect(screen.getByTestId("agents-table")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Execution graph" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByTestId("execution-graph")).toBeInTheDocument();
    // The decision panel comes before the agents table.
    const html = document.body.innerHTML;
    expect(html.indexOf("decision-panel")).toBeLessThan(html.indexOf("agents-table"));
  });

  it("says when the run does not exist", async () => {
    server.use(http.get(api("/api/runs/:id"), () => HttpResponse.json({ detail: "Run not found" }, { status: 404 })), ...defaultHandlers());
    renderRun();
    expect(await screen.findByText("Run not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to all runs" })).toHaveAttribute("href", "/runs");
  });

  it("shows an error with retry for other failures", async () => {
    let calls = 0;
    server.use(
      http.get(api("/api/runs/:id"), () => {
        calls += 1;
        return calls === 1 ? HttpResponse.json({ detail: "db down" }, { status: 500 }) : HttpResponse.json(makeRunDetail({ id: RUN_ID }));
      }),
      ...defaultHandlers(),
    );
    renderRun();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load this run");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByTestId("decision-panel")).toBeInTheDocument());
  });

  it("opens the agent inspector from an agents table row", async () => {
    useRun();
    renderRun();
    await userEvent.click(await screen.findByRole("row", { name: "Open Network agent" }));
    expect(useInspectorStore.getState().agentExecutionId).toBe("a1");
  });

  it("switches between prompts, defaulting to the newest", async () => {
    const first = makeIteration({ id: "i1", sequence: 1, objective: "First prompt", decision: makeDecision({ summary: "First decision" }) });
    const second = makeIteration({
      id: "i2",
      sequence: 2,
      objective: "Second prompt",
      agent_executions: [makeAgent({ id: "a2", agent_type: "CARGO", recommendation: { cargo_stance: "SUPPORTS", confidence: 0.7, cited_sources: [] } })],
      decision: makeDecision({ id: "d2", summary: "Second decision" }),
    });
    useRun(makeRunDetail({ id: RUN_ID, iterations: [first, second] }));
    renderRun();
    await waitFor(() => expect(screen.getByTestId("decision-summary-text")).toHaveTextContent("Second decision"));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Second prompt");
    expect(screen.getByText("Cargo")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "1" }));
    expect(screen.getByTestId("decision-summary-text")).toHaveTextContent("First decision");
    expect(screen.getByText("Network")).toBeInTheDocument();
    // Picking the newest again resumes following it.
    await userEvent.click(screen.getByRole("button", { name: "2" }));
    expect(screen.getByTestId("decision-summary-text")).toHaveTextContent("Second decision");
  });

  it("follows a new prompt that arrives while the page is open", async () => {
    const first = makeIteration({ id: "i1", sequence: 1, decision: makeDecision({ summary: "First decision" }) });
    useRun(makeRunDetail({ id: RUN_ID, iterations: [first] }));
    const { queryClient } = renderRun();
    await waitFor(() => expect(screen.getByTestId("decision-summary-text")).toHaveTextContent("First decision"));
    act(() => {
      queryClient.setQueryData(runKeys.detail(RUN_ID), makeRunDetail({
        id: RUN_ID,
        iterations: [first, makeIteration({ id: "i2", sequence: 2, decision: makeDecision({ summary: "Live decision" }) })],
      }));
    });
    await waitFor(() => expect(screen.getByTestId("decision-summary-text")).toHaveTextContent("Live decision"));
  });

  it("renders a pending prompt without a decision", async () => {
    useRun(
      makeRunDetail({
        id: RUN_ID,
        status: "RUNNING",
        completed_at: null,
        iterations: [makeIteration({ status: "RUNNING", decision: null, agent_executions: [] })],
      }),
    );
    renderRun();
    expect(await screen.findByTestId("decision-empty")).toHaveTextContent(/still working/);
    expect(screen.getByText("No agents have started yet")).toBeInTheDocument();
  });

  it("falls back to run-level data when the run has no iterations", async () => {
    useRun(makeRunDetail({ id: RUN_ID, iterations: [], decision: makeDecision({ summary: "Legacy decision" }) }));
    renderRun();
    await waitFor(() => expect(screen.getByTestId("decision-summary-text")).toHaveTextContent("Legacy decision"));
    expect(screen.queryByRole("group", { name: "Prompt" })).not.toBeInTheDocument();
  });

  it("renders an older decision that has no score or breakdown", async () => {
    useRun(
      makeRunDetail({
        id: RUN_ID,
        iterations: [makeIteration({ decision: makeDecision({ validation_result: { risk: "LOW", constraints: "PASS" } }) })],
      }),
    );
    renderRun();
    expect(await screen.findByTestId("breakdown-missing")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Decision score: no score" })).toBeInTheDocument();
  });

  it("shows evidence, messages and events in their tabs", async () => {
    useRun();
    server.use(
      http.get(api("/api/runs/:id/messages"), () =>
        HttpResponse.json([{ id: "m1", run_id: RUN_ID, context_id: null, sender: "NETWORK", receiver: "FLEET", message_type: "ROUTE_SELECTED", payload: {}, created_at: "2026-10-15T10:00:10Z" }]),
      ),
      http.get(api("/api/events"), () =>
        HttpResponse.json([
          { id: "e1", run_id: RUN_ID, agent_execution_id: null, event_type: "orchestration.completed", severity: "INFO", entity_type: null, entity_id: null, payload: {}, created_at: "2026-10-15T10:00:40Z" },
        ]),
      ),
    );
    renderRun();
    await screen.findByTestId("decision-panel");

    await userEvent.click(screen.getByRole("tab", { name: /Evidence/ }));
    expect(await screen.findByTestId("evidence-group-eia_jet_fuel")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Evidence/ })).toHaveTextContent("2");

    await userEvent.click(screen.getByRole("tab", { name: "Messages" }));
    expect(await screen.findByTestId("messages-tab")).toHaveTextContent("ROUTE_SELECTED");

    await userEvent.click(screen.getByRole("tab", { name: "Events" }));
    expect(await screen.findByText("orchestration.completed")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Knowledge graph" }));
    expect(await screen.findByText("[NO AGENT KNOWLEDGE YET]")).toBeInTheDocument();
  });

  it("cites evidence titles on the agents table", async () => {
    useRun();
    renderRun();
    const chip = await screen.findByText("fuel:eia:2026-10-10");
    await waitFor(() => expect(chip).toHaveAttribute("title", "Jet fuel, US Gulf Coast (fuel:eia:2026-10-10)"));
  });

  it("works when evidence fails to load (the badge is simply absent)", async () => {
    useRun();
    server.use(http.get(api("/api/runs/:id/evidence"), () => HttpResponse.json({ detail: "x" }, { status: 500 })));
    renderRun();
    const tab = await screen.findByRole("tab", { name: /Evidence/ });
    await waitFor(() => expect(within(tab).queryByText(/^\d+$/)).toBeNull());
  });
});
