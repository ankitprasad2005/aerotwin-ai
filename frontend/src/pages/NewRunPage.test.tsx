import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { useEventStreamStore } from "../stores/eventStreamStore";
import { api } from "../test/fixtures";
import { server } from "../test/mswServer";
import { renderWithProviders } from "../test/render";
import type { EventRecord } from "../types";
import { MAX_OBJECTIVE_LENGTH, NewRunPage, OBJECTIVE_TEMPLATES } from "./NewRunPage";

const RUN = { id: "run-9", objective: "Grow", status: "COMPLETED", created_at: "2026-10-15T10:00:00Z", completed_at: null };

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/new" element={<NewRunPage />} />
      <Route path="/runs/:id" element={<Where />} />
    </Routes>,
    { route: "/new" },
  );
}

function startedEvent(patch: Partial<EventRecord> = {}): EventRecord {
  return {
    id: "ev-new",
    run_id: "run-live",
    agent_execution_id: null,
    event_type: "orchestration.started",
    severity: "INFO",
    entity_type: null,
    entity_id: null,
    payload: { objective: "Grow cargo", iteration: 1 },
    created_at: "2026-10-15T10:00:00Z",
    ...patch,
  };
}

beforeEach(() => {
  useEventStreamStore.getState().clear();
});

describe("NewRunPage", () => {
  it("disables submit for an empty or whitespace-only objective", async () => {
    renderPage();
    const submit = screen.getByRole("button", { name: "Run orchestration" });
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Objective"), "   ");
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Objective"), "x");
    expect(submit).toBeEnabled();
  });

  it("fills the objective from a template chip", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: OBJECTIVE_TEMPLATES[1] }));
    expect(screen.getByLabelText("Objective")).toHaveValue(OBJECTIVE_TEMPLATES[1]);
    expect(screen.getByTestId("objective-counter")).toHaveTextContent(`${OBJECTIVE_TEMPLATES[1].length} / 2000`);
  });

  it("caps the objective at 2000 characters and warns near the limit", () => {
    renderPage();
    fireEvent.change(screen.getByLabelText("Objective"), { target: { value: "a".repeat(2500) } });
    expect(screen.getByLabelText<HTMLTextAreaElement>("Objective").value).toHaveLength(MAX_OBJECTIVE_LENGTH);
    expect(screen.getByTestId("objective-counter")).toHaveTextContent("2000 / 2000");
    expect(screen.getByTestId("objective-counter")).toHaveClass("text-warn");
  });

  it("submits the trimmed objective and goes to the run when the POST answers", async () => {
    let body: unknown = null;
    server.use(
      http.post(api("/api/runs"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(RUN);
      }),
    );
    renderPage();
    await userEvent.type(screen.getByLabelText("Objective"), "  Grow cargo  ");
    await userEvent.click(screen.getByRole("button", { name: "Run orchestration" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/runs/run-9"));
    expect(body).toEqual({ objective: "Grow cargo" });
  });

  it("goes to the run as soon as its start event arrives, before the POST finishes", async () => {
    server.use(
      http.post(api("/api/runs"), async () => {
        await new Promise((resolve) => setTimeout(resolve, 300));
        return HttpResponse.json({ ...RUN, id: "run-live" });
      }),
    );
    renderPage();
    await userEvent.type(screen.getByLabelText("Objective"), "Grow cargo");
    await userEvent.click(screen.getByRole("button", { name: "Run orchestration" }));
    expect(screen.getByRole("button", { name: "Starting…" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(/taken to the run/);
    expect(screen.getByLabelText("Objective")).toBeDisabled();
    act(() => useEventStreamStore.getState().addEvent(startedEvent()));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/runs/run-live"));
  });

  it("ignores start events for other objectives and events that were already there", async () => {
    useEventStreamStore.getState().addEvent(startedEvent({ id: "old", run_id: "run-old" }));
    server.use(
      http.post(api("/api/runs"), async () => {
        await new Promise((resolve) => setTimeout(resolve, 200));
        return HttpResponse.json({ ...RUN, id: "run-post" });
      }),
    );
    renderPage();
    await userEvent.type(screen.getByLabelText("Objective"), "Grow cargo");
    await userEvent.click(screen.getByRole("button", { name: "Run orchestration" }));
    act(() => useEventStreamStore.getState().addEvent(startedEvent({ id: "other", run_id: "run-other", payload: { objective: "Something else" } })));
    act(() => useEventStreamStore.getState().addEvent(startedEvent({ id: "done", run_id: "run-x", event_type: "orchestration.completed" })));
    act(() => useEventStreamStore.getState().addEvent(startedEvent({ id: "norun", run_id: null })));
    expect(screen.queryByTestId("where")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/runs/run-post"));
  });

  it("navigates only once when both the event and the response arrive", async () => {
    server.use(http.post(api("/api/runs"), async () => {
      await new Promise((resolve) => setTimeout(resolve, 100));
      return HttpResponse.json({ ...RUN, id: "run-live" });
    }));
    renderPage();
    await userEvent.type(screen.getByLabelText("Objective"), "Grow cargo");
    await userEvent.click(screen.getByRole("button", { name: "Run orchestration" }));
    act(() => useEventStreamStore.getState().addEvent(startedEvent()));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/runs/run-live"));
  });

  it("shows the server's error and lets the user try again", async () => {
    server.use(http.post(api("/api/runs"), () => HttpResponse.json({ detail: "LLM provider is not configured" }, { status: 503 })));
    renderPage();
    await userEvent.type(screen.getByLabelText("Objective"), "Grow cargo");
    await userEvent.click(screen.getByRole("button", { name: "Run orchestration" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not start the run: LLM provider is not configured");
    expect(screen.getByRole("button", { name: "Run orchestration" })).toBeEnabled();
    expect(screen.getByLabelText("Objective")).toHaveValue("Grow cargo");
  });

  it("submits with Ctrl+Enter but not with a plain Enter", async () => {
    let calls = 0;
    server.use(http.post(api("/api/runs"), () => {
      calls += 1;
      return HttpResponse.json(RUN);
    }));
    renderPage();
    await userEvent.type(screen.getByLabelText("Objective"), "Grow");
    await userEvent.keyboard("{Enter}");
    expect(calls).toBe(0);
    await userEvent.keyboard("{Control>}{Enter}{/Control}");
    await waitFor(() => expect(calls).toBe(1));
  });

  it("does nothing on Ctrl+Enter with an empty objective", async () => {
    renderPage();
    screen.getByLabelText("Objective").focus();
    await userEvent.keyboard("{Control>}{Enter}{/Control}");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run orchestration" })).toBeDisabled();
  });
});
