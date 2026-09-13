import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/mswServer";
import { OrchestrationPage } from "./OrchestrationPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <OrchestrationPage />
    </QueryClientProvider>,
  );
}

describe("OrchestrationPage", () => {
  it("renders the page title, objective form, and run picker", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])));
    renderPage();
    expect(screen.getByTestId("page-content")).toBeInTheDocument();
    expect(screen.getByText("ORCHESTRATION")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /RUN ORCHESTRATION/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("View run")).toBeInTheDocument());
  });

  it("shows a placeholder prompt when no run is selected", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("[SELECT OR START A RUN TO VIEW ITS EXECUTION GRAPH]")).toBeInTheDocument(),
    );
  });

  it("selects the newly created run after a successful submission", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])));
    server.use(
      http.post("http://localhost:8000/api/runs", () =>
        HttpResponse.json({
          id: "new-run-1",
          objective: "x",
          status: "COMPLETED",
          created_at: "2026-09-11T00:00:00Z",
          completed_at: "2026-09-11T00:00:05Z",
        }),
      ),
    );
    renderPage();
    await userEvent.type(screen.getByPlaceholderText(/Improve airline profitability/), "x");
    await userEvent.click(screen.getByRole("button", { name: /RUN ORCHESTRATION/ }));
    await waitFor(() => expect(screen.getByTestId("graph-placeholder")).toHaveTextContent("new-run-1"));
  });

  it("lists fetched runs as options in the run picker", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () =>
        HttpResponse.json([
          {
            id: "1",
            objective: "Improve profitability",
            status: "COMPLETED",
            created_at: "2026-09-11T00:00:00Z",
            completed_at: null,
          },
        ]),
      ),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("Improve profitability (COMPLETED)")).toBeInTheDocument());
  });

  it("shows the execution graph placeholder for a run selected from the picker", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () =>
        HttpResponse.json([
          {
            id: "1",
            objective: "Improve profitability",
            status: "COMPLETED",
            created_at: "2026-09-11T00:00:00Z",
            completed_at: null,
          },
        ]),
      ),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("Improve profitability (COMPLETED)")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("View run"), "1");
    expect(screen.getByTestId("graph-placeholder")).toHaveTextContent("1");

    await userEvent.selectOptions(screen.getByLabelText("View run"), "");
    expect(screen.getByText("[SELECT OR START A RUN TO VIEW ITS EXECUTION GRAPH]")).toBeInTheDocument();
  });
});
