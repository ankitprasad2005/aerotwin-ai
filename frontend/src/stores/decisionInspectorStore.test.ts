import { describe, expect, it } from "vitest";
import { useInspectorStore } from "./inspectorStore";
import { useDecisionInspectorStore } from "./decisionInspectorStore";

describe("decisionInspectorStore", () => {
  it("defaults to no decision selected", () => {
    useDecisionInspectorStore.setState({ decisionId: null });
    expect(useDecisionInspectorStore.getState().decisionId).toBeNull();
  });

  it("open() sets the selected decision id", () => {
    useDecisionInspectorStore.getState().open("1");
    expect(useDecisionInspectorStore.getState().decisionId).toBe("1");
  });

  it("close() clears the selected decision id", () => {
    useDecisionInspectorStore.getState().open("1");
    useDecisionInspectorStore.getState().close();
    expect(useDecisionInspectorStore.getState().decisionId).toBeNull();
  });

  it("closes the agent inspector when a decision is opened", () => {
    useInspectorStore.getState().open("agent-1");
    useDecisionInspectorStore.getState().open("decision-1");
    expect(useInspectorStore.getState().agentExecutionId).toBeNull();
    expect(useDecisionInspectorStore.getState().decisionId).toBe("decision-1");
  });
});
