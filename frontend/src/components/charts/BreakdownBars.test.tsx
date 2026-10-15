import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BreakdownBars, StackedBar } from "./BreakdownBars";

describe("BreakdownBars", () => {
  it("renders a labelled meter per row with its detail", () => {
    render(
      <BreakdownBars
        label="Score breakdown"
        items={[
          { key: "profit", label: "Profit", fraction: 0.62, detail: "+18.6", tone: "ok", hint: "Weekly profit" },
          { key: "risk", label: "Risk", fraction: 0.4 },
        ]}
      />,
    );
    expect(screen.getByRole("list", { name: "Score breakdown" })).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Profit" })).toHaveAttribute("aria-valuenow", "62");
    expect(screen.getByText("+18.6")).toBeInTheDocument();
    expect(screen.getAllByTestId("bar-fill")[0]).toHaveStyle({ width: "62%" });
  });

  it("clamps out-of-range and non-finite fractions", () => {
    render(
      <BreakdownBars
        label="b"
        items={[
          { key: "a", label: "A", fraction: 5 },
          { key: "b", label: "B", fraction: -1 },
          { key: "c", label: "C", fraction: Number.NaN },
        ]}
      />,
    );
    expect(screen.getByRole("meter", { name: "A" })).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByRole("meter", { name: "B" })).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByRole("meter", { name: "C" })).toHaveAttribute("aria-valuenow", "0");
  });

  it("shows a message when there is nothing to show", () => {
    render(<BreakdownBars label="b" items={[]} />);
    expect(screen.getByTestId("breakdown-empty")).toBeInTheDocument();
  });
});

describe("StackedBar", () => {
  const segments = [
    { key: "r", label: "Recommend", value: 6, tone: "ok" as const },
    { key: "v", label: "Review", value: 3, tone: "warn" as const },
    { key: "x", label: "Reject", value: 0, tone: "bad" as const },
  ];

  it("sizes segments by share and omits empty ones from the bar", () => {
    render(<StackedBar label="Decisions" segments={segments} />);
    const parts = screen.getAllByTestId("stack-segment");
    expect(parts).toHaveLength(2);
    expect(parts[0]).toHaveStyle({ width: "66.66666666666666%" });
    expect(screen.getByRole("img", { name: "Decisions: Recommend 6, Review 3, Reject 0" })).toBeInTheDocument();
    // Legend still lists every verdict, including the zero one.
    expect(screen.getByText("Reject")).toBeInTheDocument();
  });

  it("says there is no data when the total is zero or values are invalid", () => {
    render(
      <StackedBar
        label="Decisions"
        segments={[
          { key: "a", label: "A", value: 0, tone: "ok" },
          { key: "b", label: "B", value: Number.NaN, tone: "bad" },
          { key: "c", label: "C", value: -4, tone: "warn" },
        ]}
      />,
    );
    expect(screen.getByRole("img", { name: "Decisions: no data" })).toBeInTheDocument();
    expect(screen.queryByTestId("stack-segment")).not.toBeInTheDocument();
  });
});
