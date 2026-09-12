import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Label, MonoText } from "./MonoText";

describe("MonoText", () => {
  it("renders children with the mono font class", () => {
    render(<MonoText>4,821</MonoText>);
    expect(screen.getByText("4,821")).toHaveClass("font-mono");
  });
});

describe("Label", () => {
  it("renders children with uppercase label styling", () => {
    render(<Label>TOKENS</Label>);
    const el = screen.getByText("TOKENS");
    expect(el).toHaveClass("font-mono");
    expect(el).toHaveClass("uppercase");
    expect(el).toHaveClass("text-text-secondary");
  });
});
