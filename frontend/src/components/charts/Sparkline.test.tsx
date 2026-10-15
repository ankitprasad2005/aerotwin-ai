import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Sparkline } from "./Sparkline";

describe("Sparkline", () => {
  it("draws a line and an end dot for a series", () => {
    const { container } = render(<Sparkline values={[1, 3, 2, 5]} label="Runs per day" />);
    expect(screen.getByRole("img", { name: "Runs per day" })).toBeInTheDocument();
    expect(screen.getByTestId("sparkline-line").getAttribute("d")).toMatch(/^M[\d.]+ [\d.]+ L/);
    expect(container.querySelector("circle")).not.toBeNull();
    expect(container.querySelectorAll("path")).toHaveLength(2); // area + line
  });

  it("shows an empty baseline and says so in the accessible name", () => {
    render(<Sparkline values={[]} label="Tokens" />);
    expect(screen.getByRole("img", { name: "Tokens: no data" })).toBeInTheDocument();
    expect(screen.getByTestId("sparkline-empty")).toBeInTheDocument();
  });

  it("treats a series of only non-finite values as empty", () => {
    render(<Sparkline values={[null, Number.NaN, undefined]} label="Fuel" />);
    expect(screen.getByTestId("sparkline-empty")).toBeInTheDocument();
  });

  it("renders a single point as a short tick without an area", () => {
    const { container } = render(<Sparkline values={[4]} label="One" tone="ok" />);
    expect(container.querySelectorAll("path")).toHaveLength(1);
    expect(screen.getByTestId("sparkline-line").getAttribute("d")).toMatch(/^M[\d.]+ [\d.]+ L[\d.]+ [\d.]+$/);
  });

  it("honours size and tone", () => {
    render(<Sparkline values={[1, 2]} label="Sized" width={120} height={40} tone="bad" />);
    const svg = screen.getByRole("img");
    expect(svg).toHaveAttribute("width", "120");
    expect(svg).toHaveAttribute("height", "40");
    expect(screen.getByTestId("sparkline-line")).toHaveAttribute("stroke", "var(--c-bad)");
  });

  it("copes with a flat series", () => {
    render(<Sparkline values={[3, 3, 3]} label="Flat" />);
    expect(screen.getByTestId("sparkline-line").getAttribute("d")).not.toContain("NaN");
  });
});
