import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { useEventStreamStore } from "../../stores/eventStreamStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import { makeAgent } from "../../test/fixtures";
import { AgentsTable } from "./AgentsTable";

beforeEach(() => {
  useInspectorStore.getState().close();
  useEventStreamStore.getState().clear();
});

describe("AgentsTable", () => {
  it("shows one row per agent with status, time, tokens, confidence, recommendation and citations", () => {
    render(
      <AgentsTable
        executions={[
          makeAgent(),
          makeAgent({ id: "a2", agent_type: "FLEET", elapsed_ms: 900, total_tokens: 500, recommendation: { aircraft_tail_number: "VT-ABC", assignment_action: "REASSIGN", route: "BOM-DEL", confidence: 0.5, cited_sources: [] } }),
        ]}
        titles={{ "fuel:eia:2026-10-10": "Jet fuel, US Gulf Coast" }}
      />,
    );
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(screen.getByText("Network")).toBeInTheDocument();
    expect(screen.getByText("4.2 s")).toBeInTheDocument();
    expect(screen.getByText("1,800")).toBeInTheDocument();
    expect(screen.getByText("900 ms")).toBeInTheDocument();
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText(/BOM-DEL: increase frequency/)).toBeInTheDocument();
    expect(screen.getByText("fuel:eia:2026-10-10")).toHaveAttribute("title", "Jet fuel, US Gulf Coast (fuel:eia:2026-10-10)");
    // Low confidence is highlighted; no citations reads "none".
    expect(screen.getByText("50%")).toHaveClass("text-warn");
    expect(screen.getByText("none")).toBeInTheDocument();
  });

  it("opens the inspector on click, Enter and Space", async () => {
    render(<AgentsTable executions={[makeAgent({ id: "a1" })]} />);
    const row = screen.getByRole("row", { name: "Open Network agent" });
    await userEvent.click(row);
    expect(useInspectorStore.getState().agentExecutionId).toBe("a1");
    useInspectorStore.getState().close();
    row.focus();
    await userEvent.keyboard("{Enter}");
    expect(useInspectorStore.getState().agentExecutionId).toBe("a1");
    useInspectorStore.getState().close();
    await userEvent.keyboard(" ");
    expect(useInspectorStore.getState().agentExecutionId).toBe("a1");
    useInspectorStore.getState().close();
    await userEvent.keyboard("x");
    expect(useInspectorStore.getState().agentExecutionId).toBeNull();
  });

  it("renders dashes for an agent that has not finished", () => {
    render(
      <AgentsTable
        executions={[makeAgent({ status: "QUEUED", recommendation: null, elapsed_ms: null, total_tokens: null })]}
      />,
    );
    const cells = screen.getAllByRole("cell");
    expect(cells.filter((cell) => cell.textContent === "—").length).toBeGreaterThanOrEqual(4);
  });

  it("uses the live status for an unfinished agent, but never overrides a final one", () => {
    useEventStreamStore.setState({ agentExecutionStatuses: { a1: "WAITING_FOR_LLM", a2: "RUNNING" } });
    render(
      <AgentsTable
        executions={[makeAgent({ id: "a1", status: "QUEUED" }), makeAgent({ id: "a2", agent_type: "FLEET", status: "COMPLETED" })]}
      />,
    );
    expect(screen.getByText("WAITING_FOR_LLM")).toBeInTheDocument();
    expect(screen.queryByText("RUNNING")).not.toBeInTheDocument();
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
  });

  it("falls back to the stored status when there is no live one", () => {
    render(<AgentsTable executions={[makeAgent({ status: "RETRYING" })]} />);
    expect(screen.getByText("RETRYING")).toBeInTheDocument();
  });

  it("collapses many citations into a +N counter", () => {
    const cited = ["a", "b", "c", "d", "e"];
    render(<AgentsTable executions={[makeAgent({ recommendation: { confidence: 0.9, cited_sources: cited } })]} />);
    expect(screen.getByText("+2")).toHaveAttribute("title", "d, e");
    expect(screen.queryByText("d")).not.toBeInTheDocument();
    expect(screen.getByText("a")).toHaveAttribute("title", "a");
  });

  it("shows an empty state with no agents", () => {
    render(<AgentsTable executions={[]} />);
    expect(screen.getByText("No agents have started yet")).toBeInTheDocument();
  });
});
