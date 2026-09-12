import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { ReactElement } from "react";
import { server } from "../../test/mswServer";
import { RecentRunsList } from "./RecentRunsList";

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("RecentRunsList", () => {
  it("shows a loading state before data arrives", () => {
    server.use(
      http.get("http://localhost:8000/api/runs", async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json([]);
      }),
    );
    renderWithClient(<RecentRunsList />);
    expect(screen.getByText("[LOADING...]")).toBeInTheDocument();
  });

  it("shows an empty state when there are no runs", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])));
    renderWithClient(<RecentRunsList />);
    await waitFor(() => expect(screen.getByText("[NO RUNS YET]")).toBeInTheDocument());
  });

  it("renders each run's objective and status", async () => {
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
    renderWithClient(<RecentRunsList />);
    await waitFor(() => expect(screen.getByText("Improve profitability")).toBeInTheDocument());
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );
    renderWithClient(<RecentRunsList />);
    await waitFor(() => expect(screen.getByText("[ERROR LOADING RUNS]")).toBeInTheDocument());
  });
});
