import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { api, makeStatsRun } from "../test/fixtures";
import { server } from "../test/mswServer";
import { renderWithProviders } from "../test/render";
import { RunsPage } from "./RunsPage";

const RUNS = [
  makeStatsRun({ id: "1", objective: "Improve profitability" }),
  makeStatsRun({ id: "2", objective: "Cut fuel costs", status: "FAILED", decision: null }),
  makeStatsRun({
    id: "3",
    objective: "Protect load factor",
    decision: { summary: "Reduce frequency", verdict: "REJECT", score: 20, expected_profit_impact: -100, risk: "HIGH" },
  }),
];

function useRuns(runs = RUNS) {
  server.use(http.get(api("/api/stats/runs"), () => HttpResponse.json(runs)));
}

describe("RunsPage", () => {
  it("shows a loading state and then the runs table", async () => {
    useRuns();
    renderWithProviders(<RunsPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading runs");
    expect(await screen.findByTestId("runs-table")).toBeInTheDocument();
    expect(screen.getByText("Showing 3 of 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New run" })).toHaveAttribute("href", "/new");
  });

  it("requests up to 100 runs", async () => {
    let limit: string | null = null;
    server.use(
      http.get(api("/api/stats/runs"), ({ request }) => {
        limit = new URL(request.url).searchParams.get("limit");
        return HttpResponse.json([]);
      }),
    );
    renderWithProviders(<RunsPage />);
    await screen.findByText("No runs yet");
    expect(limit).toBe("100");
  });

  it("shows an empty state that points to a new run", async () => {
    useRuns([]);
    renderWithProviders(<RunsPage />);
    expect(await screen.findByText("No runs yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start your first run" })).toHaveAttribute("href", "/new");
    expect(screen.queryByText(/Showing/)).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    let calls = 0;
    server.use(
      http.get(api("/api/stats/runs"), () => {
        calls += 1;
        return calls === 1 ? HttpResponse.json({ detail: "db down" }, { status: 500 }) : HttpResponse.json(RUNS);
      }),
    );
    renderWithProviders(<RunsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("db down");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("runs-table")).toBeInTheDocument();
  });

  it("filters by status, verdict and search text, and can clear the filters", async () => {
    useRuns();
    renderWithProviders(<RunsPage />);
    await screen.findByTestId("runs-table");
    expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Status"), "FAILED");
    expect(screen.getByText("Showing 1 of 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cut fuel costs" })).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Status"), "");
    await userEvent.selectOptions(screen.getByLabelText("Verdict"), "REJECT");
    expect(screen.getByText("Showing 1 of 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Protect load factor" })).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Verdict"), "NONE");
    expect(screen.getByText("Showing 1 of 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cut fuel costs" })).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Verdict"), "");
    await userEvent.type(screen.getByLabelText("Search"), "profit");
    expect(screen.getByText("Showing 1 of 3")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByText("Showing 3 of 3")).toBeInTheDocument();
    expect(screen.getByLabelText("Search")).toHaveValue("");
  });

  it("explains when filters match nothing and offers to clear them", async () => {
    useRuns();
    renderWithProviders(<RunsPage />);
    await screen.findByTestId("runs-table");
    await userEvent.type(screen.getByLabelText("Search"), "zzz-no-match");
    expect(screen.getByText("No runs match these filters")).toBeInTheDocument();
    await userEvent.click(within(screen.getByText("No runs match these filters").parentElement as HTMLElement).getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(screen.getByTestId("runs-table")).toBeInTheDocument());
  });
});
