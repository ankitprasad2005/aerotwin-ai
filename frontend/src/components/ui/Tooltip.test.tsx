import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Tooltip } from "./Tooltip";

describe("Tooltip", () => {
  it("is hidden until hovered, then shows and hides again", async () => {
    render(
      <Tooltip content="Explains the thing">
        <button type="button">Trigger</button>
      </Tooltip>,
    );
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    await userEvent.hover(screen.getByRole("button"));
    expect(screen.getByRole("tooltip")).toHaveTextContent("Explains the thing");
    await userEvent.unhover(screen.getByRole("button"));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("shows on keyboard focus and links itself with aria-describedby", async () => {
    render(
      <Tooltip content="Help" side="right">
        <button type="button">Trigger</button>
      </Tooltip>,
    );
    await userEvent.tab();
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toHaveClass("left-full");
    expect(screen.getByRole("button").parentElement).toHaveAttribute("aria-describedby", tooltip.id);
    await userEvent.tab();
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    render(
      <Tooltip content="Help" className="extra">
        <button type="button">Trigger</button>
      </Tooltip>,
    );
    await userEvent.hover(screen.getByRole("button"));
    fireEvent.keyDown(screen.getByRole("button"), { key: "a" });
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("button"), { key: "Escape" });
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
