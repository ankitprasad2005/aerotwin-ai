import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WeightGroup } from "./WeightGroup";

const ROWS = [
  { key: "a", label: "Alpha", help: "First" },
  { key: "b", label: "Beta" },
] as const;

function renderGroup(values: Record<"a" | "b", number>, onChange = vi.fn()) {
  render(<WeightGroup title="Factors" description="Explains" rows={ROWS} values={values} onChange={onChange} />);
  return onChange;
}

describe("WeightGroup", () => {
  it("shows each weight, its normalised share and the raw total", () => {
    renderGroup({ a: 0.3, b: 0.9 });
    expect(screen.getByRole("group", { name: "Factors" })).toBeInTheDocument();
    expect(screen.getByLabelText("Alpha weight")).toHaveValue(0.3);
    expect(screen.getByTestId("share-a")).toHaveTextContent("25%");
    expect(screen.getByTestId("share-b")).toHaveTextContent("75%");
    expect(screen.getByTestId("weight-total")).toHaveTextContent("1.20");
  });

  it("reports slider and number-input changes", () => {
    const onChange = renderGroup({ a: 0.5, b: 0.5 });
    fireEvent.change(screen.getByLabelText("Alpha weight slider"), { target: { value: "0.8" } });
    expect(onChange).toHaveBeenLastCalledWith("a", 0.8);
    fireEvent.change(screen.getByLabelText("Beta weight"), { target: { value: "2.5" } });
    expect(onChange).toHaveBeenLastCalledWith("b", 2.5);
  });

  it("reports an emptied number input as NaN so the form can flag it", () => {
    const onChange = renderGroup({ a: 0.5, b: 0.5 });
    fireEvent.change(screen.getByLabelText("Alpha weight"), { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith("a", Number.NaN);
  });

  it("copes with NaN, negative and huge values without breaking the slider or shares", () => {
    renderGroup({ a: Number.NaN, b: -3 });
    expect(screen.getByLabelText("Alpha weight")).toHaveValue(null);
    expect(screen.getByLabelText("Alpha weight slider")).toHaveValue("0");
    expect(screen.getByTestId("share-a")).toHaveTextContent("0%");
    expect(screen.getByTestId("weight-total")).toHaveTextContent("-3.00");
  });

  it("clamps the slider position for values above the slider range", () => {
    renderGroup({ a: 5, b: 0 });
    expect(screen.getByLabelText("Alpha weight slider")).toHaveValue("1");
    expect(screen.getByTestId("share-a")).toHaveTextContent("100%");
  });

  it("ignores non-finite values in the total", () => {
    renderGroup({ a: Number.POSITIVE_INFINITY, b: 1 });
    expect(screen.getByTestId("weight-total")).toHaveTextContent("1.00");
  });
});
