import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";

describe("Button", () => {
  it("renders its children", () => {
    render(<Button>RUN ORCHESTRATION</Button>);
    expect(screen.getByText("RUN ORCHESTRATION")).toBeInTheDocument();
  });

  it("applies the accent background for the primary variant by default", () => {
    render(<Button>GO</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-accent");
  });

  it("applies a border style for the ghost variant", () => {
    render(<Button variant="ghost">CANCEL</Button>);
    expect(screen.getByRole("button")).toHaveClass("border-border-visible");
  });

  it("fires onClick when clicked", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>GO</Button>);
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not fire onClick when disabled", async () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabled>
        GO
      </Button>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).not.toHaveBeenCalled();
  });
});
