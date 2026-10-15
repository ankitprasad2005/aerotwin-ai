import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusPill } from "./StatusPill";

describe("StatusPill", () => {
  it("renders the status text in uppercase label style", () => {
    render(<StatusPill status="COMPLETED" />);
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
  });

  it("shows a pulse dot for RUNNING (a live state)", () => {
    render(<StatusPill status="RUNNING" />);
    expect(screen.getByTestId("status-pulse")).toBeInTheDocument();
  });

  it("shows a pulse dot for WAITING_FOR_LLM (a live state)", () => {
    render(<StatusPill status="WAITING_FOR_LLM" />);
    expect(screen.getByTestId("status-pulse")).toBeInTheDocument();
  });

  it("does not show a pulse dot for COMPLETED (a terminal state)", () => {
    render(<StatusPill status="COMPLETED" />);
    expect(screen.queryByTestId("status-pulse")).not.toBeInTheDocument();
  });

  it("applies the red color class for FAILED", () => {
    render(<StatusPill status="FAILED" />);
    expect(screen.getByText("FAILED")).toHaveClass("text-bad");
  });

  it("applies the green color class for COMPLETED", () => {
    render(<StatusPill status="COMPLETED" />);
    expect(screen.getByText("COMPLETED")).toHaveClass("text-ok");
  });

  it("falls back to the muted color class for an unrecognized status", () => {
    render(<StatusPill status="SOMETHING_UNKNOWN" />);
    expect(screen.getByText("SOMETHING_UNKNOWN")).toHaveClass("text-muted");
  });
});
