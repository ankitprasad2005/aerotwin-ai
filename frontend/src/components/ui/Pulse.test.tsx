import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Pulse } from "./Pulse";

describe("Pulse", () => {
  it("renders a green dot when active", () => {
    render(<Pulse active />);
    expect(screen.getByTestId("pulse-dot")).toHaveClass("bg-ok");
  });

  it("accepts a custom colour class", () => {
    render(<Pulse active className="bg-bad" />);
    expect(screen.getByTestId("pulse-dot")).toHaveClass("bg-bad");
  });

  it("renders nothing when inactive", () => {
    render(<Pulse active={false} />);
    expect(screen.queryByTestId("pulse-dot")).not.toBeInTheDocument();
  });
});
