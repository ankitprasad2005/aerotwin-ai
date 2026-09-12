import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Panel } from "./Panel";

describe("Panel", () => {
  it("renders its children", () => {
    render(<Panel>content</Panel>);
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("applies the surface background and border by default", () => {
    render(<Panel data-testid="panel">content</Panel>);
    expect(screen.getByTestId("panel")).toHaveClass("bg-surface");
    expect(screen.getByTestId("panel")).toHaveClass("border-border");
  });

  it("merges an additional className", () => {
    render(
      <Panel data-testid="panel" className="p-lg">
        content
      </Panel>,
    );
    expect(screen.getByTestId("panel")).toHaveClass("p-lg");
    expect(screen.getByTestId("panel")).toHaveClass("bg-surface");
  });
});
