import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LineChart } from "./LineChart";

const data = [
  { x: "2026-10-01", y: 2.1 },
  { x: "2026-10-02", y: 2.3 },
  { x: "2026-10-03", y: 2.2 },
];

function mockRect(element: Element) {
  element.getBoundingClientRect = () => ({ left: 0, width: 560, top: 0, height: 160, right: 560, bottom: 160, x: 0, y: 0, toJSON: () => ({}) });
}

describe("LineChart", () => {
  it("renders a line, a labelled summary and the first and last x labels", () => {
    render(<LineChart data={data} label="Jet fuel" formatY={(v) => `$${v.toFixed(2)}`} />);
    expect(screen.getByRole("img", { name: "Jet fuel, 3 points, from $2.10 to $2.20" })).toBeInTheDocument();
    expect(screen.getByTestId("linechart-line").getAttribute("d")).not.toContain("NaN");
    expect(screen.getByText("2026-10-01")).toBeInTheDocument();
    expect(screen.getByText("2026-10-03")).toBeInTheDocument();
  });

  it("shows an empty state for no data", () => {
    render(<LineChart data={[]} label="FX" />);
    expect(screen.getByTestId("linechart-empty")).toHaveTextContent("No data yet");
    expect(screen.getByRole("img", { name: "FX: no data" })).toBeInTheDocument();
  });

  it("shows an empty state when every value is non-finite", () => {
    render(<LineChart data={[{ x: "a", y: Number.NaN }]} label="Bad" />);
    expect(screen.getByTestId("linechart-empty")).toBeInTheDocument();
  });

  it("draws a single point as a dot with one x label", () => {
    const { container } = render(<LineChart data={[{ x: "2026-10-01", y: 5 }]} label="One" />);
    expect(container.querySelector("circle")).not.toBeNull();
    expect(screen.getAllByText("2026-10-01")).toHaveLength(1);
  });

  it("reads out the nearest point on hover and clears on leave", () => {
    render(<LineChart data={data} label="Fuel" formatY={(v) => v.toFixed(1)} formatX={(x) => x.slice(5)} />);
    const svg = screen.getByTestId("linechart");
    mockRect(svg);
    fireEvent.mouseMove(svg, { clientX: 560 });
    expect(screen.getByTestId("linechart-readout")).toHaveTextContent("10-03: 2.2");
    fireEvent.mouseMove(svg, { clientX: 0 });
    expect(screen.getByTestId("linechart-readout")).toHaveTextContent("10-01: 2.1");
    fireEvent.mouseLeave(svg);
    expect(screen.queryByTestId("linechart-readout")).not.toBeInTheDocument();
  });

  it("supports keyboard navigation with the arrow keys and Escape", () => {
    render(<LineChart data={data} label="Fuel" />);
    const svg = screen.getByTestId("linechart");
    fireEvent.keyDown(svg, { key: "ArrowRight" });
    expect(screen.getByTestId("linechart-readout")).toHaveTextContent("2026-10-01");
    fireEvent.keyDown(svg, { key: "ArrowRight" });
    fireEvent.keyDown(svg, { key: "ArrowRight" });
    fireEvent.keyDown(svg, { key: "ArrowRight" }); // clamps at the last point
    expect(screen.getByTestId("linechart-readout")).toHaveTextContent("2026-10-03");
    fireEvent.keyDown(svg, { key: "ArrowLeft" });
    expect(screen.getByTestId("linechart-readout")).toHaveTextContent("2026-10-02");
    fireEvent.keyDown(svg, { key: "Escape" });
    expect(screen.queryByTestId("linechart-readout")).not.toBeInTheDocument();
    fireEvent.keyDown(svg, { key: "ArrowLeft" }); // from nothing, starts at the last point
    expect(screen.getByTestId("linechart-readout")).toHaveTextContent("2026-10-03");
    fireEvent.keyDown(svg, { key: "Tab" });
    fireEvent.blur(svg);
    expect(screen.queryByTestId("linechart-readout")).not.toBeInTheDocument();
  });

  it("clamps ArrowLeft at the first point and puts the readout on the left of the right half", () => {
    render(<LineChart data={data} label="Fuel" />);
    const svg = screen.getByTestId("linechart");
    fireEvent.keyDown(svg, { key: "ArrowRight" });
    fireEvent.keyDown(svg, { key: "ArrowLeft" });
    fireEvent.keyDown(svg, { key: "ArrowLeft" });
    expect(screen.getByTestId("linechart-readout")).toHaveTextContent("2026-10-01");
    mockRect(svg);
    fireEvent.mouseMove(svg, { clientX: 560 });
    expect(screen.getByTestId("linechart-readout").querySelector("text")).toHaveAttribute("text-anchor", "end");
  });

  it("copes with a flat series and skips NaN entries", () => {
    render(<LineChart data={[{ x: "a", y: 3 }, { x: "b", y: Number.NaN }, { x: "c", y: 3 }]} label="Flat" />);
    expect(screen.getByRole("img", { name: /2 points/ })).toBeInTheDocument();
    expect(screen.getByTestId("linechart-line").getAttribute("d")).not.toContain("NaN");
  });
});
