import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GraphNodeContent } from "./GraphNodeContent";

describe("GraphNodeContent", () => {
  it("renders the node label and status", () => {
    render(<GraphNodeContent label="NETWORK_AGENT" status="RUNNING" />);
    expect(screen.getByText("NETWORK_AGENT")).toBeInTheDocument();
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
  });
});
