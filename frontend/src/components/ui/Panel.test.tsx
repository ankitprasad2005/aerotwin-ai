import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Panel } from "./Panel";

describe("Panel", () => {
  it("renders its children inside a bordered panel", () => {
    render(<Panel data-testid="panel">content</Panel>);
    expect(screen.getByText("content")).toBeInTheDocument();
    expect(screen.getByTestId("panel")).toHaveClass("bg-panel");
    expect(screen.getByTestId("panel")).toHaveClass("border-line");
  });

  it("renders a title bar with actions", () => {
    render(
      <Panel title="Fuel price" actions={<button type="button">Refresh</button>}>
        body
      </Panel>,
    );
    expect(screen.getByRole("heading", { name: "Fuel price" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
  });

  it("renders a title bar for actions alone", () => {
    render(<Panel actions={<span>act</span>}>body</Panel>);
    expect(screen.getByText("act")).toBeInTheDocument();
  });

  it("has no title bar without a title or actions", () => {
    render(<Panel>body</Panel>);
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });

  it("pads the body unless told not to, and merges className", () => {
    const { rerender } = render(<Panel className="mt-4">body</Panel>);
    expect(screen.getByText("body")).toHaveClass("p-3");
    expect(screen.getByText("body").closest("section")).toHaveClass("mt-4");
    rerender(<Panel padded={false}>body</Panel>);
    expect(screen.getByText("body")).not.toHaveClass("p-3");
  });
});
