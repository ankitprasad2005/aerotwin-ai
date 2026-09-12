import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Pulse } from "./Pulse";

describe("Pulse", () => {
  it("renders a dot when active", () => {
    render(<Pulse active />);
    expect(screen.getByTestId("pulse-dot")).toBeInTheDocument();
  });

  it("renders nothing when inactive", () => {
    render(<Pulse active={false} />);
    expect(screen.queryByTestId("pulse-dot")).not.toBeInTheDocument();
  });
});
