import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EmptyState, ErrorState, LoadingState } from "./States";

describe("LoadingState", () => {
  it("announces a default and a custom label", () => {
    const { rerender } = render(<LoadingState />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading…");
    rerender(<LoadingState label="Loading runs…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading runs…");
  });
});

describe("ErrorState", () => {
  it("shows a default title and the error message", () => {
    render(<ErrorState error={new Error("HTTP 500")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.getByRole("alert")).toHaveTextContent("HTTP 500");
  });

  it("omits the detail for non-Error values and empty messages", () => {
    const { rerender } = render(<ErrorState title="Could not load" error="string" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load");
    expect(screen.getByRole("alert")).not.toHaveTextContent("string");
    rerender(<ErrorState error={new Error("")} />);
    expect(screen.getByRole("alert").querySelectorAll("div")).toHaveLength(1);
  });

  it("offers a retry only when given a handler", async () => {
    const onRetry = vi.fn();
    const { rerender } = render(<ErrorState />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    rerender(<ErrorState onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe("EmptyState", () => {
  it("renders a title, hint and action", () => {
    render(<EmptyState title="No runs yet" hint="Start one." action={<button type="button">New run</button>} />);
    expect(screen.getByText("No runs yet")).toBeInTheDocument();
    expect(screen.getByText("Start one.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New run" })).toBeInTheDocument();
  });

  it("works with just a title", () => {
    render(<EmptyState title="Nothing here" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });
});
