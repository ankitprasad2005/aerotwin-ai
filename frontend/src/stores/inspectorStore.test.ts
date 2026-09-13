import { describe, expect, it } from "vitest";
import { useDecisionInspectorStore } from "./decisionInspectorStore";
import { useInspectorStore } from "./inspectorStore";

describe("inspectorStore", () => {
  it("defaults to no agent execution selected", () => {
    useInspectorStore.setState({ agentExecutionId: null });
    expect(useInspectorStore.getState().agentExecutionId).toBeNull();
  });

  it("open() sets the selected agent execution id", () => {
    useInspectorStore.getState().open("1");
    expect(useInspectorStore.getState().agentExecutionId).toBe("1");
  });

  it("close() clears the selected agent execution id", () => {
    useInspectorStore.getState().open("1");
    useInspectorStore.getState().close();
    expect(useInspectorStore.getState().agentExecutionId).toBeNull();
  });

  it("closes the decision inspector when an agent execution is opened", () => {
    useDecisionInspectorStore.getState().open("decision-1");
    useInspectorStore.getState().open("agent-1");
    expect(useDecisionInspectorStore.getState().decisionId).toBeNull();
    expect(useInspectorStore.getState().agentExecutionId).toBe("agent-1");
  });
});
