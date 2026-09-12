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

  it("renders its children when open", () => {
    render(
      <SlideOver open onClose={vi.fn()}>
        content
      </SlideOver>,
    );
    expect(screen.getByText("content")).toBeInTheDocument();
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
});
