import { create } from "zustand";
import type { EventRecord } from "../types";

const MAX_EVENTS = 2000;

interface EventStreamState {
  events: EventRecord[];
  runStatuses: Record<string, string>;
  agentExecutionStatuses: Record<string, string>;
  // Which run each agent execution belongs to, so consumers can tell when an agent's live
  // status is stale because its run has already finished.
  agentExecutionRunIds: Record<string, string>;
  addEvent: (event: EventRecord) => void;
  clear: () => void;
}

function deriveRunStatus(eventType: string): string | null {
  if (eventType === "orchestration.started") return "RUNNING";
  if (eventType === "orchestration.completed") return "COMPLETED";
  if (eventType === "orchestration.failed") return "FAILED";
  return null;
}

function deriveAgentExecutionStatus(eventType: string): string | null {
  switch (eventType) {
    case "agent.started":
    case "context.created":
    case "tool.completed":
      return "RUNNING";
    case "tool.called":
      return "WAITING_FOR_TOOL";
    case "llm.request":
      return "WAITING_FOR_LLM";
    case "agent.completed":
      return "COMPLETED";
    case "agent.failed":
      return "FAILED";
    default:
      return null;
  }
}

export const useEventStreamStore = create<EventStreamState>((set) => ({
  events: [],
  runStatuses: {},
  agentExecutionStatuses: {},
  agentExecutionRunIds: {},
  addEvent: (event) =>
    set((state) => {
      const events = [event, ...state.events].slice(0, MAX_EVENTS);

      const runStatuses = { ...state.runStatuses };
      if (event.run_id) {
        const nextStatus = deriveRunStatus(event.event_type);
        if (nextStatus) runStatuses[event.run_id] = nextStatus;
      }

      const agentExecutionStatuses = { ...state.agentExecutionStatuses };
      let agentExecutionRunIds = state.agentExecutionRunIds;
      if (event.agent_execution_id) {
        const nextStatus = deriveAgentExecutionStatus(event.event_type);
        if (nextStatus) agentExecutionStatuses[event.agent_execution_id] = nextStatus;
        if (event.run_id && agentExecutionRunIds[event.agent_execution_id] !== event.run_id) {
          agentExecutionRunIds = { ...agentExecutionRunIds, [event.agent_execution_id]: event.run_id };
        }
      }

      return { events, runStatuses, agentExecutionStatuses, agentExecutionRunIds };
    }),
  clear: () => set({ events: [], runStatuses: {}, agentExecutionStatuses: {}, agentExecutionRunIds: {} }),
}));
