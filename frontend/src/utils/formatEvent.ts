import type { EventRecord } from "../types";

function sourceFromEventType(eventType: string): string {
  if (eventType.startsWith("orchestration.")) return "ORCHESTRATOR";
  if (eventType.startsWith("agent.")) return "AGENT";
  if (eventType.startsWith("context.")) return "CONTEXT ENGINE";
  if (eventType.startsWith("tool.")) return "TOOL";
  if (eventType.startsWith("llm.")) return "LLM";
  if (eventType.startsWith("decision.")) return "DECISION ENGINE";
  return "SYSTEM";
}

function messageFromEvent(event: EventRecord): string {
  switch (event.event_type) {
    case "orchestration.started":
      return "New optimization objective received.";
    case "orchestration.completed":
      return "Orchestration completed.";
    case "orchestration.failed":
      return `Orchestration failed: ${String(event.payload.reason ?? "unknown reason")}`;
    case "context.created":
      return "Context created.";
    case "agent.started":
      return `Task created (${String(event.payload.agent_type ?? "agent")}).`;
    case "agent.completed":
      return "Agent completed.";
    case "agent.failed":
      return "Agent failed.";
    case "tool.called":
      return `Requesting ${String(event.payload.tool_name ?? "tool")}().`;
    case "tool.completed":
      return "Tool completed.";
    case "tool.failed":
      return `Tool failed: ${String(event.payload.error ?? "unknown error")}`;
    case "llm.request":
      return "Sending context to external LLM.";
    case "llm.response":
      return "LLM response received.";
    case "llm.failed":
      return `LLM call failed: ${String(event.payload.error ?? "unknown error")}`;
    case "decision.created":
      return `Decision created: ${String(event.payload.summary ?? "")}`;
    default:
      return event.event_type;
  }
}

export function formatEventTimestamp(isoTimestamp: string): string {
  return new Date(isoTimestamp).toLocaleTimeString("en-GB", { hour12: false });
}

export function formatEventLine(event: EventRecord): { timestamp: string; source: string; message: string } {
  return {
    timestamp: formatEventTimestamp(event.created_at),
    source: sourceFromEventType(event.event_type),
    message: messageFromEvent(event),
  };
}
