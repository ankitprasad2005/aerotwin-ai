import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { api } from "../../test/fixtures";
import { server } from "../../test/mswServer";
import { renderWithProviders } from "../../test/render";
import type { AgentMessage } from "../../types/api";
import { MessagesTab } from "./MessagesTab";

function message(patch: Partial<AgentMessage> = {}): AgentMessage {
  return {
    id: "m1",
    run_id: "run-1",
    context_id: null,
    sender: "NETWORK",
    receiver: "FLEET",
    message_type: "ROUTE_SELECTED",
    payload: { route: "BOM-DEL", action: "INCREASE_FREQUENCY" },
    created_at: "2026-10-15T10:00:10Z",
    ...patch,
  };
}

describe("MessagesTab", () => {
  it("lists messages with sender, receiver, type and an expandable payload", async () => {
    server.use(http.get(api("/api/runs/:id/messages"), () => HttpResponse.json([message(), message({ id: "m2", sender: "orchestrator", receiver: "DECISION_ENGINE", message_type: "DONE", payload: {} })])));
    renderWithProviders(<MessagesTab runId="run-1" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading messages");
    await waitFor(() => expect(screen.getByTestId("messages-tab")).toBeInTheDocument());
    expect(screen.getByText("Network")).toBeInTheDocument();
    expect(screen.getByText("Fleet")).toBeInTheDocument();
    expect(screen.getByText("ROUTE_SELECTED")).toBeInTheDocument();
    // Non agent-type names pass through unchanged; all-caps names are prettified.
    expect(screen.getByText("orchestrator")).toBeInTheDocument();
    expect(screen.getByText("Decision engine")).toBeInTheDocument();
    expect(screen.getByText("2 fields")).toBeInTheDocument();
    expect(screen.getByText("0 fields")).toBeInTheDocument();
    await userEvent.click(screen.getByText("2 fields"));
    expect(screen.getByText(/"route": "BOM-DEL"/)).toBeInTheDocument();
  });

  it("uses the singular for a one-field payload", async () => {
    server.use(http.get(api("/api/runs/:id/messages"), () => HttpResponse.json([message({ payload: { a: 1 } })])));
    renderWithProviders(<MessagesTab runId="run-1" />);
    expect(await screen.findByText("1 field")).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    server.use(http.get(api("/api/runs/:id/messages"), () => HttpResponse.json([])));
    renderWithProviders(<MessagesTab runId="run-1" />);
    expect(await screen.findByText("No messages were exchanged")).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    let calls = 0;
    server.use(
      http.get(api("/api/runs/:id/messages"), () => {
        calls += 1;
        return calls === 1 ? HttpResponse.json({ detail: "run not found" }, { status: 404 }) : HttpResponse.json([message()]);
      }),
    );
    renderWithProviders(<MessagesTab runId="run-1" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("run not found");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByTestId("messages-tab")).toBeInTheDocument());
  });
});
