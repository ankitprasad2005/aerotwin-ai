import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "../../test/mswServer";
import { ObjectiveForm } from "./ObjectiveForm";

function renderForm(onRunCreated = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ObjectiveForm onRunCreated={onRunCreated} />
    </QueryClientProvider>,
  );
  return { onRunCreated };
}

describe("ObjectiveForm", () => {
  it("disables the submit button when the objective is empty", () => {
    renderForm();
    expect(screen.getByRole("button", { name: /RUN ORCHESTRATION/ })).toBeDisabled();
  });

  it("enables the submit button once an objective is typed", async () => {
    renderForm();
    await userEvent.type(screen.getByPlaceholderText(/Improve airline profitability/), "Improve profitability");
    expect(screen.getByRole("button", { name: /RUN ORCHESTRATION/ })).toBeEnabled();
  });

  it("submits the objective and calls onRunCreated with the new run id", async () => {
    server.use(
      http.post("http://localhost:8000/api/runs", async ({ request }) => {
        const body = (await request.json()) as { objective: string };
        return HttpResponse.json({
          id: "new-run-1",
          objective: body.objective,
          status: "COMPLETED",
          created_at: "2026-09-11T00:00:00Z",
          completed_at: "2026-09-11T00:00:05Z",
        });
      }),
    );
    const { onRunCreated } = renderForm();
    await userEvent.type(screen.getByPlaceholderText(/Improve airline profitability/), "Improve profitability");
    await userEvent.click(screen.getByRole("button", { name: /RUN ORCHESTRATION/ }));
    await waitFor(() => expect(onRunCreated).toHaveBeenCalledWith("new-run-1"));
  });

  it("shows an error message when run creation fails", async () => {
    server.use(
      http.post("http://localhost:8000/api/runs", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );
    renderForm();
    await userEvent.type(screen.getByPlaceholderText(/Improve airline profitability/), "Improve profitability");
    await userEvent.click(screen.getByRole("button", { name: /RUN ORCHESTRATION/ }));
    await waitFor(() => expect(screen.getByText(/\[ERROR:/)).toBeInTheDocument());
  });
});
