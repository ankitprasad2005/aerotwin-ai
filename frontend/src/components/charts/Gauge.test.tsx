import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Gauge, toneForScore } from "./Gauge";

describe("toneForScore", () => {
  const thresholds = { review: 45, recommend: 70 };
  it("is green at and above the recommend threshold", () => {
    expect(toneForScore(70, thresholds)).toBe("ok");
    expect(toneForScore(100, thresholds)).toBe("ok");
  });
  it("is amber from the review threshold up to recommend", () => {
    expect(toneForScore(45, thresholds)).toBe("warn");
    expect(toneForScore(69.9, thresholds)).toBe("warn");
  });
  it("is red below the review threshold", () => {
    expect(toneForScore(44.9, thresholds)).toBe("bad");
    expect(toneForScore(0, thresholds)).toBe("bad");
  });
});

describe("Gauge", () => {
  it("shows the rounded score, a filled arc and an accessible name", () => {
    render(<Gauge value={80.6} label="Decision score" />);
    expect(screen.getByRole("img", { name: "Decision score: 81 out of 100" })).toBeInTheDocument();
    expect(screen.getByText("81")).toBeInTheDocument();
    expect(screen.getByTestId("gauge-fill")).toHaveAttribute("stroke", "var(--c-ok)");
    expect(screen.getAllByTestId("gauge-tick")).toHaveLength(2);
  });

  it("colours amber and red scores", () => {
    const { rerender } = render(<Gauge value={70} label="s" />);
    expect(screen.getByTestId("gauge-fill")).toHaveAttribute("stroke", "var(--c-warn)");
    rerender(<Gauge value={10} label="s" />);
    expect(screen.getByTestId("gauge-fill")).toHaveAttribute("stroke", "var(--c-bad)");
  });

  it("renders a dash and no arc when there is no score", () => {
    render(<Gauge value={null} label="Decision score" />);
    expect(screen.getByRole("img", { name: "Decision score: no score" })).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByTestId("gauge-fill")).not.toBeInTheDocument();
  });

  it("draws no fill for a zero score and clamps out-of-range values", () => {
    const { rerender } = render(<Gauge value={0} label="s" />);
    expect(screen.queryByTestId("gauge-fill")).not.toBeInTheDocument();
    rerender(<Gauge value={250} label="s" />);
    expect(screen.getByTestId("gauge-fill").getAttribute("d")).not.toContain("NaN");
  });

  it("treats NaN as no score and uses custom thresholds and size", () => {
    render(<Gauge value={Number.NaN} label="s" thresholds={{ review: 20, recommend: 30 }} size={200} />);
    expect(screen.getByTestId("gauge")).toHaveAttribute("width", "200");
    expect(screen.getByText(/review 20 · recommend 30/)).toBeInTheDocument();
    expect(screen.queryByTestId("gauge-fill")).not.toBeInTheDocument();
  });
});
