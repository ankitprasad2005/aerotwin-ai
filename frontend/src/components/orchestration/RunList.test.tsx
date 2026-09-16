import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "../../test/mswServer";
import { RunList } from "./RunList";

const RUNS = [
  {
    id: "1",
    objective: "Improve profitability",
    status: "COMPLETED",
    created_at: "2026-09-11T00:00:00Z",
    completed_at: "2026-09-11T00:00:06Z",
  },
  {
    id: "2",
    objective: "Cut costs on thin routes",
    status: "FAILED",
    created_at: "2026-09-11T00:10:00Z",
    completed_at: null,
  },
];

function renderList(selectedRunId: string | null = null, onSelect = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <RunList selectedRunId={selectedRunId} onSelect={onSelect} />
    </QueryClientProvider>,
  );
  return { onSelect };
}

describe("RunList", () => {
  it("shows a loading state first", () => {
    server.use(
      http.get("http://localhost:8000/api/runs", async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json([]);
      }),
    );
    renderList();
    expect(screen.getByText("[LOADING RUNS...]")).toBeInTheDocument();
  });

  it("lists every run with its status", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json(RUNS)));
    renderList();

    await waitFor(() => expect(screen.getByTestId("run-list")).toBeInTheDocument());
    expect(screen.getByText("Improve profitability")).toBeInTheDocument();
    expect(screen.getByText("Cut costs on thin routes")).toBeInTheDocument();
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
    expect(screen.getByText("FAILED")).toBeInTheDocument();
  });

  it("marks the selected run and reports clicks", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json(RUNS)));
    const { onSelect } = renderList("1");

    await waitFor(() => expect(screen.getByTestId("run-list")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Improve profitability/ })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: /Cut costs/ })).not.toHaveAttribute("aria-current");

    await userEvent.click(screen.getByRole("button", { name: /Cut costs/ }));
    expect(onSelect).toHaveBeenCalledWith("2");
  });

  it("shows an empty state when there are no runs", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])));
    renderList();
    await waitFor(() => expect(screen.getByText("[NO RUNS YET]")).toBeInTheDocument());
  });

  it("shows an error state when the request fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );
    renderList();
    await waitFor(() => expect(screen.getByText("[ERROR LOADING RUNS]")).toBeInTheDocument());
  });
});
