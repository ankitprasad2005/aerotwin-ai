import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

// Temporary placeholder test for the Task 1 scaffolding placeholder App.
// Fully replaced in Task 7 once App.tsx becomes the real app shell.
describe("App", () => {
  it("renders the scaffolding placeholder", () => {
    render(<App />);
    expect(screen.getByText(/AeroTwin AI/)).toBeInTheDocument();
  });
});
