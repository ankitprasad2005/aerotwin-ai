import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Sidebar } from "./Sidebar";

describe("Sidebar", () => {
  it("renders links to all three top-level destinations", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    expect(screen.getByText("DASHBOARD")).toBeInTheDocument();
    expect(screen.getByText("ORCHESTRATION")).toBeInTheDocument();
    expect(screen.getByText("EVENTS")).toBeInTheDocument();
  });

  it("marks the current route's link as active", () => {
    render(
      <MemoryRouter initialEntries={["/orchestration"]}>
        <Sidebar />
      </MemoryRouter>,
    );
    expect(screen.getByText("ORCHESTRATION")).toHaveClass("text-accent");
    expect(screen.getByText("DASHBOARD")).not.toHaveClass("text-accent");
  });
});
