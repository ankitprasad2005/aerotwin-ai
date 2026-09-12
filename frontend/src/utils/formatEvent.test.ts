import { describe, expect, it } from "vitest";
import type { EventRecord } from "../types";
import { formatEventLine, formatEventTimestamp } from "./formatEvent";

function makeEvent(overrides: Partial<EventRecord>): EventRecord {
  return {
    id: "1",
    run_id: null,
    agent_execution_id: null,
    event_type: "orchestration.started",
    severity: "INFO",
    entity_type: null,
    entity_id: null,
    payload: {},
    created_at: "2026-09-11T09:42:31Z",
    ...overrides,
  };
}

describe("formatEventTimestamp", () => {
  it("formats an ISO timestamp as HH:MM:SS", () => {
    expect(formatEventTimestamp("2026-09-11T09:42:31Z")).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  });
});

describe("formatEventLine", () => {
  it("labels orchestration.started events as ORCHESTRATOR with a descriptive message", () => {
    const line = formatEventLine(makeEvent({ event_type: "orchestration.started" }));
    expect(line.source).toBe("ORCHESTRATOR");
    expect(line.message).toBe("New optimization objective received.");
  });

  it("includes the tool name for tool.called events", () => {
    const line = formatEventLine(
      makeEvent({ event_type: "tool.called", payload: { tool_name: "query_route_profitability" } }),
    );
    expect(line.source).toBe("TOOL");
    expect(line.message).toBe("Requesting query_route_profitability().");
  });

  it("includes the failure reason for orchestration.failed", () => {
    const line = formatEventLine(
      makeEvent({ event_type: "orchestration.failed", payload: { reason: "network agent failed" } }),
    );
    expect(line.message).toBe("Orchestration failed: network agent failed");
  });

  it("falls back to 'unknown reason' when orchestration.failed has no reason in its payload", () => {
    const line = formatEventLine(makeEvent({ event_type: "orchestration.failed", payload: {} }));
    expect(line.message).toBe("Orchestration failed: unknown reason");
  });

  it("falls back to 'tool' when tool.called has no tool_name in its payload", () => {
    const line = formatEventLine(makeEvent({ event_type: "tool.called", payload: {} }));
    expect(line.message).toBe("Requesting tool().");
  });

  it("labels decision.created events as DECISION ENGINE with the summary", () => {
    const line = formatEventLine(
      makeEvent({ event_type: "decision.created", payload: { summary: "Increase BOM-DEL frequency" } }),
    );
    expect(line.source).toBe("DECISION ENGINE");
    expect(line.message).toBe("Decision created: Increase BOM-DEL frequency");
  });

  it("falls back to the raw event type and SYSTEM source for an unrecognized event", () => {
    const line = formatEventLine(makeEvent({ event_type: "digital_twin.updated" }));
    expect(line.source).toBe("SYSTEM");
    expect(line.message).toBe("digital_twin.updated");
  });

  it.each([
    ["orchestration.completed", {}, "ORCHESTRATOR", "Orchestration completed."],
    ["context.created", {}, "CONTEXT ENGINE", "Context created."],
    ["agent.started", { agent_type: "NETWORK" }, "AGENT", "Task created (NETWORK)."],
    ["agent.started", {}, "AGENT", "Task created (agent)."],
    ["agent.completed", {}, "AGENT", "Agent completed."],
    ["agent.failed", {}, "AGENT", "Agent failed."],
    ["tool.completed", {}, "TOOL", "Tool completed."],
    ["tool.failed", { error: "timeout" }, "TOOL", "Tool failed: timeout"],
    ["tool.failed", {}, "TOOL", "Tool failed: unknown error"],
    ["llm.request", {}, "LLM", "Sending context to external LLM."],
    ["llm.response", {}, "LLM", "LLM response received."],
    ["llm.failed", { error: "rate limited" }, "LLM", "LLM call failed: rate limited"],
    ["llm.failed", {}, "LLM", "LLM call failed: unknown error"],
    ["decision.created", {}, "DECISION ENGINE", "Decision created: "],
  ] as const)("formats %s events", (eventType, payload, expectedSource, expectedMessage) => {
    const line = formatEventLine(makeEvent({ event_type: eventType, payload }));
    expect(line.source).toBe(expectedSource);
    expect(line.message).toBe(expectedMessage);
  });
});
