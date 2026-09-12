import { beforeEach, describe, expect, it } from "vitest";
import type { EventRecord } from "../types";
import { useEventStreamStore } from "./eventStreamStore";

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
    created_at: "2026-09-11T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  useEventStreamStore.getState().clear();
});

describe("eventStreamStore", () => {
  it("prepends new events (newest first)", () => {
    useEventStreamStore.getState().addEvent(makeEvent({ id: "1" }));
    useEventStreamStore.getState().addEvent(makeEvent({ id: "2" }));
    expect(useEventStreamStore.getState().events.map((e) => e.id)).toEqual(["2", "1"]);
  });

  it("caps the event list at 2000 entries", () => {
    for (let i = 0; i < 2005; i += 1) {
      useEventStreamStore.getState().addEvent(makeEvent({ id: String(i) }));
    }
    expect(useEventStreamStore.getState().events).toHaveLength(2000);
  });

  it("sets run status to RUNNING on orchestration.started", () => {
    useEventStreamStore.getState().addEvent(makeEvent({ run_id: "run-1", event_type: "orchestration.started" }));
    expect(useEventStreamStore.getState().runStatuses["run-1"]).toBe("RUNNING");
  });

  it("sets run status to COMPLETED on orchestration.completed", () => {
    useEventStreamStore.getState().addEvent(makeEvent({ run_id: "run-1", event_type: "orchestration.completed" }));
    expect(useEventStreamStore.getState().runStatuses["run-1"]).toBe("COMPLETED");
  });

  it("sets run status to FAILED on orchestration.failed", () => {
    useEventStreamStore.getState().addEvent(makeEvent({ run_id: "run-1", event_type: "orchestration.failed" }));
    expect(useEventStreamStore.getState().runStatuses["run-1"]).toBe("FAILED");
  });

  it("sets agent execution status to WAITING_FOR_LLM on llm.request", () => {
    useEventStreamStore.getState().addEvent(makeEvent({ agent_execution_id: "agent-1", event_type: "llm.request" }));
    expect(useEventStreamStore.getState().agentExecutionStatuses["agent-1"]).toBe("WAITING_FOR_LLM");
  });

  it("sets agent execution status to WAITING_FOR_TOOL on tool.called", () => {
    useEventStreamStore.getState().addEvent(makeEvent({ agent_execution_id: "agent-1", event_type: "tool.called" }));
    expect(useEventStreamStore.getState().agentExecutionStatuses["agent-1"]).toBe("WAITING_FOR_TOOL");
  });

  it("sets agent execution status to COMPLETED on agent.completed", () => {
    useEventStreamStore.getState().addEvent(makeEvent({ agent_execution_id: "agent-1", event_type: "agent.completed" }));
    expect(useEventStreamStore.getState().agentExecutionStatuses["agent-1"]).toBe("COMPLETED");
  });

  it("sets agent execution status to FAILED on agent.failed", () => {
    useEventStreamStore.getState().addEvent(makeEvent({ agent_execution_id: "agent-1", event_type: "agent.failed" }));
    expect(useEventStreamStore.getState().agentExecutionStatuses["agent-1"]).toBe("FAILED");
  });

  it("leaves status maps untouched for events with no run_id/agent_execution_id", () => {
    useEventStreamStore.getState().addEvent(makeEvent({ event_type: "decision.created" }));
    expect(useEventStreamStore.getState().runStatuses).toEqual({});
    expect(useEventStreamStore.getState().agentExecutionStatuses).toEqual({});
  });

  it("clear() resets events and status maps", () => {
    useEventStreamStore.getState().addEvent(makeEvent({ run_id: "run-1" }));
    useEventStreamStore.getState().clear();
    expect(useEventStreamStore.getState().events).toEqual([]);
    expect(useEventStreamStore.getState().runStatuses).toEqual({});
  });
});
