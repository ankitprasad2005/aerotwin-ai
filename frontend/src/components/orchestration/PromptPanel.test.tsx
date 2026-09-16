import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/mswServer";
import { PromptPanel } from "./PromptPanel";

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PromptPanel runId="r1" />
    </QueryClientProvider>,
  );
}

describe("PromptPanel", () => {
  it("stays disabled until a prompt is typed", async () => {
    renderPanel();
    const submit = screen.getByRole("button", { name: /ADD PROMPT/ });
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Follow-up prompt"), "Protect load factor");
    expect(submit).toBeEnabled();
  });

  it("posts the prompt to the run and clears the field", async () => {
    let received: unknown = null;
    server.use(
      http.post("http://localhost:8000/api/runs/r1/prompts", async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({
          id: "r1",
          objective: "Improve profitability",
          status: "COMPLETED",
          created_at: "2026-09-11T00:00:00Z",
          completed_at: "2026-09-11T00:01:00Z",
        });
      }),
    );
    renderPanel();

    await userEvent.type(screen.getByLabelText("Follow-up prompt"), "Protect load factor");
    await userEvent.click(screen.getByRole("button", { name: /ADD PROMPT/ }));

    await waitFor(() => expect(received).toEqual({ objective: "Protect load factor" }));
    await waitFor(() => expect(screen.getByLabelText("Follow-up prompt")).toHaveValue(""));
  });

  it("ignores a whitespace-only prompt", async () => {
    // No handler registered: the test setup fails the run on any unhandled request, so this also
    // proves nothing was posted.
    renderPanel();

    await userEvent.type(screen.getByLabelText("Follow-up prompt"), "   ");
    expect(screen.getByRole("button", { name: /ADD PROMPT/ })).toBeDisabled();

    // Submit the form directly: the disabled button can't be clicked, but a form can still be
    // submitted (e.g. Enter in a text input), and that path must not post either.
    fireEvent.submit(screen.getByTestId("prompt-panel"));
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(screen.getByLabelText("Follow-up prompt")).toHaveValue("   ");
  });

  it("shows that the pipeline is running while the prompt is in flight", async () => {
    server.use(
      http.post("http://localhost:8000/api/runs/r1/prompts", async () => {
        await new Promise((resolve) => setTimeout(resolve, 60));
        return HttpResponse.json({
          id: "r1",
          objective: "Improve profitability",
          status: "COMPLETED",
          created_at: "2026-09-11T00:00:00Z",
          completed_at: "2026-09-11T00:01:00Z",
        });
      }),
    );
    renderPanel();

    await userEvent.type(screen.getByLabelText("Follow-up prompt"), "Protect load factor");
    await userEvent.click(screen.getByRole("button", { name: /ADD PROMPT/ }));

    expect(screen.getByRole("button", { name: "[RUNNING...]" })).toBeDisabled();
    await waitFor(() => expect(screen.getByLabelText("Follow-up prompt")).toHaveValue(""));
  });

  it("shows an error when the run fails to accept the prompt", async () => {
    server.use(
      http.post("http://localhost:8000/api/runs/r1/prompts", () =>
        HttpResponse.json({ detail: "run not found" }, { status: 404 }),
      ),
    );
    renderPanel();

    await userEvent.type(screen.getByLabelText("Follow-up prompt"), "Protect load factor");
    await userEvent.click(screen.getByRole("button", { name: /ADD PROMPT/ }));

    await waitFor(() => expect(screen.getByText(/run not found/)).toBeInTheDocument());
  });
});
