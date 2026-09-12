import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatTile } from "./StatTile";

describe("StatTile", () => {
  it("renders the label and numeric value", () => {
    render(<StatTile label="ACTIVE RUNS" value={3} />);
    expect(screen.getByText("ACTIVE RUNS")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("is reachable by a testid derived from its label", () => {
    render(<StatTile label="FAILED" value={0} />);
    expect(screen.getByTestId("stat-tile-FAILED")).toHaveTextContent("0");
  });
});
