import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useConnectionStore } from "../../stores/connectionStore";
import { HeaderBar } from "./HeaderBar";

describe("HeaderBar", () => {
  beforeEach(() => {
    useConnectionStore.setState({ status: "connecting" });
  });

  it("shows LIVE when connection status is open", () => {
    useConnectionStore.setState({ status: "open" });
    render(<HeaderBar debugMode={false} onToggleDebug={vi.fn()} onNewRun={vi.fn()} />);
    expect(screen.getByText(/LIVE/)).toBeInTheDocument();
  });

  it("shows DISCONNECTED when connection status is closed", () => {
    useConnectionStore.setState({ status: "closed" });
    render(<HeaderBar debugMode={false} onToggleDebug={vi.fn()} onNewRun={vi.fn()} />);
    expect(screen.getByText(/DISCONNECTED/)).toBeInTheDocument();
  });

  it("calls onToggleDebug when the debug button is clicked", async () => {
    const onToggleDebug = vi.fn();
    render(<HeaderBar debugMode={false} onToggleDebug={onToggleDebug} onNewRun={vi.fn()} />);
    await userEvent.click(screen.getByText(/DEBUG/));
    expect(onToggleDebug).toHaveBeenCalledTimes(1);
  });

  it("calls onNewRun when the new run button is clicked", async () => {
    const onNewRun = vi.fn();
    render(<HeaderBar debugMode={false} onToggleDebug={vi.fn()} onNewRun={onNewRun} />);
    await userEvent.click(screen.getByText("+ NEW RUN"));
    expect(onNewRun).toHaveBeenCalledTimes(1);
  });

  it("shows DEBUG ON when debugMode is true", () => {
    render(<HeaderBar debugMode onToggleDebug={vi.fn()} onNewRun={vi.fn()} />);
    expect(screen.getByText("DEBUG ON")).toBeInTheDocument();
  });
});
