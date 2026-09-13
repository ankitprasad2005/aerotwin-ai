import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useConnectionStore } from "../../stores/connectionStore";
import { useDebugStore } from "../../stores/debugStore";
import { HeaderBar } from "./HeaderBar";

describe("HeaderBar", () => {
  beforeEach(() => {
    useConnectionStore.setState({ status: "connecting" });
    useDebugStore.setState({ enabled: false });
  });

  it("shows LIVE when connection status is open", () => {
    useConnectionStore.setState({ status: "open" });
    render(<HeaderBar onNewRun={vi.fn()} />);
    expect(screen.getByText(/LIVE/)).toBeInTheDocument();
  });

  it("shows DISCONNECTED when connection status is closed", () => {
    useConnectionStore.setState({ status: "closed" });
    render(<HeaderBar onNewRun={vi.fn()} />);
    expect(screen.getByText(/DISCONNECTED/)).toBeInTheDocument();
  });

  it("toggles debug mode when the debug button is clicked", async () => {
    render(<HeaderBar onNewRun={vi.fn()} />);
    await userEvent.click(screen.getByText(/DEBUG/));
    expect(useDebugStore.getState().enabled).toBe(true);
  });

  it("calls onNewRun when the new run button is clicked", async () => {
    const onNewRun = vi.fn();
    render(<HeaderBar onNewRun={onNewRun} />);
    await userEvent.click(screen.getByText("+ NEW RUN"));
    expect(onNewRun).toHaveBeenCalledTimes(1);
  });

  it("shows DEBUG ON when debug mode is enabled", () => {
    useDebugStore.setState({ enabled: true });
    render(<HeaderBar onNewRun={vi.fn()} />);
    expect(screen.getByText("DEBUG ON")).toBeInTheDocument();
  });
});
