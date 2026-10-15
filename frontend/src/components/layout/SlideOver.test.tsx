import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SlideOver } from "./SlideOver";

describe("SlideOver", () => {
  it("renders nothing when closed", () => {
    render(
      <SlideOver open={false} onClose={vi.fn()}>
        content
      </SlideOver>,
    );
    expect(screen.queryByText("content")).not.toBeInTheDocument();
  });

  it("renders its children in a labelled modal dialog when open", () => {
    render(
      <SlideOver open onClose={vi.fn()} label="Agent inspector">
        content
      </SlideOver>,
    );
    expect(screen.getByText("content")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Agent inspector" })).toHaveAttribute("aria-modal", "true");
  });

  it("has a default label and moves focus into the dialog", () => {
    render(
      <SlideOver open onClose={vi.fn()}>
        content
      </SlideOver>,
    );
    expect(screen.getByRole("dialog", { name: "Details" })).toHaveFocus();
  });

  it("calls onClose when the backdrop is clicked", async () => {
    const onClose = vi.fn();
    render(
      <SlideOver open onClose={onClose}>
        content
      </SlideOver>,
    );
    await userEvent.click(screen.getByTestId("slide-over-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose from the close button and on Escape, but not on other keys", async () => {
    const onClose = vi.fn();
    render(
      <SlideOver open onClose={onClose}>
        content
      </SlideOver>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Close panel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    await userEvent.keyboard("a");
    expect(onClose).toHaveBeenCalledTimes(1);
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("returns focus to the previously focused element when closed", async () => {
    function Harness() {
      return (
        <>
          <button type="button">opener</button>
        </>
      );
    }
    const { rerender } = render(<Harness />);
    screen.getByRole("button", { name: "opener" }).focus();
    rerender(
      <>
        <Harness />
        <SlideOver open onClose={vi.fn()}>
          content
        </SlideOver>
      </>,
    );
    expect(screen.getByRole("dialog")).toHaveFocus();
    rerender(
      <>
        <Harness />
        <SlideOver open={false} onClose={vi.fn()}>
          content
        </SlideOver>
      </>,
    );
    expect(screen.getByRole("button", { name: "opener" })).toHaveFocus();
  });
});
