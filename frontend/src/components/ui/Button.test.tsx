import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";

describe("Button", () => {
  it("renders its children", () => {
    render(<Button>Start run</Button>);
    expect(screen.getByText("Start run")).toBeInTheDocument();
  });

  it("uses the accent background for the primary variant by default", () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-accent");
  });

  it("styles the ghost and danger variants", () => {
    const { rerender } = render(<Button variant="ghost">Cancel</Button>);
    expect(screen.getByRole("button")).toHaveClass("border-line-strong");
    rerender(<Button variant="danger">Delete</Button>);
    expect(screen.getByRole("button")).toHaveClass("text-bad");
  });

  it("defaults to type=button so it never submits a form by accident", () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("can be a submit button and merges className", () => {
    render(
      <Button type="submit" className="self-start">
        Go
      </Button>,
    );
    expect(screen.getByRole("button")).toHaveAttribute("type", "submit");
    expect(screen.getByRole("button")).toHaveClass("self-start");
  });

  it("fires onClick when clicked", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not fire onClick when disabled", async () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabled>
        Go
      </Button>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).not.toHaveBeenCalled();
  });
});
