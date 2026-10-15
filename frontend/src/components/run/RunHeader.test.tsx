import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeIteration, makeRunDetail } from "../../test/fixtures";
import { RunHeader } from "./RunHeader";

describe("RunHeader", () => {
  it("shows the objective, status, start, duration and run id", () => {
    const run = makeRunDetail();
    render(<RunHeader run={run} iterations={run.iterations} selected={1} onSelect={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Improve airline profitability" })).toBeInTheDocument();
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
    expect(screen.getByText("40.0 s")).toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
  });

  it("hides the switcher for a single prompt", () => {
    const run = makeRunDetail();
    render(<RunHeader run={run} iterations={run.iterations} selected={1} onSelect={vi.fn()} />);
    expect(screen.queryByRole("group", { name: "Prompt" })).not.toBeInTheDocument();
  });

  it("switches between prompts and shows the selected prompt's objective", async () => {
    const onSelect = vi.fn();
    const iterations = [
      makeIteration({ id: "i1", sequence: 1, objective: "First" }),
      makeIteration({ id: "i2", sequence: 2, objective: "Second" }),
    ];
    render(<RunHeader run={makeRunDetail({ iterations })} iterations={iterations} selected={2} onSelect={onSelect} />);
    expect(screen.getByRole("heading")).toHaveTextContent("Second");
    expect(screen.getByRole("button", { name: "2" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "1" })).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(screen.getByRole("button", { name: "1" }));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("falls back to the last prompt for an unknown selection and the run objective with no iterations", () => {
    const iterations = [makeIteration({ id: "i1", sequence: 1, objective: "Only" })];
    const { rerender } = render(
      <RunHeader run={makeRunDetail({ iterations })} iterations={iterations} selected={9} onSelect={vi.fn()} />,
    );
    expect(screen.getByRole("heading")).toHaveTextContent("Only");
    rerender(<RunHeader run={makeRunDetail({ objective: "Run level" })} iterations={[]} selected={1} onSelect={vi.fn()} />);
    expect(screen.getByRole("heading")).toHaveTextContent("Run level");
  });

  it("collapses a very long objective and can expand it", async () => {
    const objective = "Improve profitability ".repeat(60).trim();
    const iterations = [makeIteration({ objective })];
    render(<RunHeader run={makeRunDetail({ iterations })} iterations={iterations} selected={1} onSelect={vi.fn()} />);
    expect(screen.getByTestId("run-objective").textContent!.length).toBeLessThan(objective.length);
    await userEvent.click(screen.getByRole("button", { name: "Show full objective" }));
    expect(screen.getByTestId("run-objective")).toHaveTextContent(objective);
    await userEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(screen.getByTestId("run-objective").textContent!.endsWith("…")).toBe(true);
  });

  it("shows a dash for the duration while the run is unfinished or the dates are invalid", () => {
    const running = makeRunDetail({ status: "RUNNING", completed_at: null });
    const { rerender } = render(<RunHeader run={running} iterations={running.iterations} selected={1} onSelect={vi.fn()} />);
    expect(screen.getByText("—", { selector: ".font-mono" })).toBeInTheDocument();
    const broken = makeRunDetail({ created_at: "nope" });
    rerender(<RunHeader run={broken} iterations={broken.iterations} selected={1} onSelect={vi.fn()} />);
    expect(screen.getByText("—", { selector: ".font-mono" })).toBeInTheDocument();
  });
});
