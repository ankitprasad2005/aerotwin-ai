import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PageHeader } from "./PageHeader";

describe("PageHeader", () => {
  it("renders a level-one title only", () => {
    render(<PageHeader title="Runs" />);
    expect(screen.getByRole("heading", { level: 1, name: "Runs" })).toBeInTheDocument();
  });

  it("renders a subtitle and actions", () => {
    render(<PageHeader title="Data" subtitle="Where evidence comes from" actions={<button type="button">Refresh</button>} />);
    expect(screen.getByText("Where evidence comes from")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
  });
});
