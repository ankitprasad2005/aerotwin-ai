import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { makeStatsRun } from "../../test/fixtures";
import { renderWithProviders } from "../../test/render";
import { RunsTable } from "./RunsTable";

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function renderTable(runs = [makeStatsRun()], compact = false) {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<RunsTable runs={runs} compact={compact} />} />
      <Route path="/runs/:id" element={<Where />} />
    </Routes>,
  );
}

describe("RunsTable", () => {
  it("shows a run's objective, status, verdict, score, profit and metrics", () => {
    renderTable();
    expect(screen.getByRole("link", { name: "Improve airline profitability" })).toHaveAttribute("href", "/runs/run-1");
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
    expect(screen.getByText("Recommend")).toBeInTheDocument();
    expect(screen.getByText("74")).toBeInTheDocument();
    expect(screen.getByText("+$85,000")).toHaveClass("text-ok");
    expect(screen.getByText("LOW")).toBeInTheDocument();
    expect(screen.getByText("12,345")).toBeInTheDocument();
    expect(screen.getByText("40.0 s")).toBeInTheDocument();
    expect(screen.getByText("Increase BOM-DEL frequency")).toBeInTheDocument();
  });

  it("renders dashes for a run without a decision or metrics", () => {
    renderTable([makeStatsRun({ status: "RUNNING", decision: null, duration_ms: null, total_tokens: null, completed_at: null })]);
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(6);
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
  });

  it("renders a decision from before weighted scoring (no verdict or score)", () => {
    renderTable([
      makeStatsRun({ decision: { summary: "Legacy", verdict: null, score: null, expected_profit_impact: -400, risk: null } }),
    ]);
    expect(screen.getByText("-$400")).toHaveClass("text-bad");
    expect(screen.queryByText("Recommend")).not.toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });

  it("hides the detail columns in compact mode", () => {
    renderTable([makeStatsRun()], true);
    expect(screen.queryByRole("columnheader", { name: "Tokens" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Risk" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Verdict" })).toBeInTheDocument();
  });

  it("navigates to the run when the row is clicked", async () => {
    renderTable();
    await userEvent.click(screen.getByText("COMPLETED"));
    expect(screen.getByTestId("where")).toHaveTextContent("/runs/run-1");
  });

  it("navigates once when the link itself is clicked", async () => {
    renderTable();
    await userEvent.click(screen.getByRole("link", { name: /Improve airline/ }));
    expect(screen.getByTestId("where")).toHaveTextContent("/runs/run-1");
  });

  it("truncates a very long objective in the cell but keeps the full text as a tooltip", () => {
    const objective = "Maximise ".repeat(100).trim();
    renderTable([makeStatsRun({ objective })]);
    const link = screen.getByRole("link");
    expect(link).toHaveClass("truncate");
    expect(link).toHaveAttribute("title", objective);
  });
});
