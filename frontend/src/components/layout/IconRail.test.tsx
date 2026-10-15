import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { IconRail, NAV_ITEMS } from "./IconRail";

function renderRail(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <IconRail />
    </MemoryRouter>,
  );
}

describe("IconRail", () => {
  it("links to every page with an accessible name", () => {
    renderRail();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    const expected: Record<string, string> = {
      Overview: "/",
      Runs: "/runs",
      "New run": "/new",
      Data: "/data",
      Weights: "/weights",
      Events: "/events",
    };
    for (const [name, href] of Object.entries(expected)) {
      expect(screen.getByRole("link", { name })).toHaveAttribute("href", href);
    }
    expect(NAV_ITEMS).toHaveLength(6);
  });

  it("marks the current page", () => {
    renderRail("/data");
    expect(screen.getByRole("link", { name: "Data" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  });

  it("keeps Runs highlighted on a run detail page, but not Overview", () => {
    renderRail("/runs/abc");
    expect(screen.getByRole("link", { name: "Runs" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  });

  it("shows a tooltip with the label on hover and focus", async () => {
    renderRail();
    await userEvent.hover(screen.getByRole("link", { name: "Weights" }));
    expect(screen.getByRole("tooltip")).toHaveTextContent("Weights");
    await userEvent.unhover(screen.getByRole("link", { name: "Weights" }));
    await userEvent.tab();
    expect(screen.getByRole("tooltip")).toHaveTextContent("Overview");
  });
});
