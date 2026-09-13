import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EventFilters } from "./EventFilters";

describe("EventFilters", () => {
  it("calls onChange with the selected severity", async () => {
    const onChange = vi.fn();
    render(<EventFilters filters={{}} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText("Severity"), "ERROR");
    expect(onChange).toHaveBeenCalledWith({ severity: "ERROR" });
  });

  it("calls onChange with the typed event type", async () => {
    const onChange = vi.fn();
    render(<EventFilters filters={{}} onChange={onChange} />);
    await userEvent.type(screen.getByLabelText("Event type"), "a");
    expect(onChange).toHaveBeenCalledWith({ event_type: "a" });
  });

  it("clears a filter when its input is emptied", async () => {
    const onChange = vi.fn();
    render(<EventFilters filters={{ run_id: "1" }} onChange={onChange} />);
    await userEvent.clear(screen.getByLabelText("Run ID"));
    expect(onChange).toHaveBeenLastCalledWith({ run_id: undefined });
  });
});
