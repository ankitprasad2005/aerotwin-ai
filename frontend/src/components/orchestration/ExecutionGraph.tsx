import { useMemo } from "react";
import { Background, ReactFlow, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useRunGraph } from "../../api/useRuns";
import { useDecisionInspectorStore } from "../../stores/decisionInspectorStore";
import { useEventStreamStore } from "../../stores/eventStreamStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import { GraphNode, type GraphNodeType } from "./GraphNode";

const NODE_TYPES = { graphNode: GraphNode };

const TERMINAL_STATUSES = new Set(["COMPLETED", "FAILED"]);

// Pipeline stage decides the column, the prompt's iteration decides the row, so a run with
// several prompts reads top-to-bottom with each stage lined up (the old index-based grid wrapped
// mid-pipeline and made the edges unreadable).
const STAGE_COLUMN: Record<string, number> = {
  ORCHESTRATOR: 0,
  CONTEXT_ENGINE: 1,
  DECISION_ENGINE: 3,
  FINAL_DECISION: 4,
};

function stageColumn(nodeType: string): number {
  return STAGE_COLUMN[nodeType] ?? 2; // every *_AGENT shares the middle column
}

export function ExecutionGraph({ runId }: { runId: string }) {
  const { data: graph, isLoading, isError } = useRunGraph(runId);
  const agentExecutionStatuses = useEventStreamStore((state) => state.agentExecutionStatuses);
  const runStatuses = useEventStreamStore((state) => state.runStatuses);
  const openInspector = useInspectorStore((state) => state.open);
  const openDecision = useDecisionInspectorStore((state) => state.open);

  const nodes = useMemo<GraphNodeType[]>(() => {
    if (!graph) return [];
    const usedCells = new Map<string, number>();
    return graph.nodes.map((node) => {
      // A terminal status from the backend is final, so live statuses only fill in progress
      // for nodes that haven't finished — they must not overwrite COMPLETED/FAILED with a stale
      // in-progress status (e.g. the completion event was missed during a WebSocket reconnect).
      let liveStatus = node.status;
      if (TERMINAL_STATUSES.has(node.status)) {
        // keep the backend's final status
      } else if (node.agent_execution_id && agentExecutionStatuses[node.agent_execution_id]) {
        liveStatus = agentExecutionStatuses[node.agent_execution_id];
      } else if (node.type === "ORCHESTRATOR" && runStatuses[runId]) {
        liveStatus = runStatuses[runId];
      }
      const column = stageColumn(node.type);
      const row = (node.iteration ?? 1) - 1;
      const cell = `${row}-${column}`;
      const offset = usedCells.get(cell) ?? 0;
      usedCells.set(cell, offset + 1);

      return {
        id: node.id,
        type: "graphNode" as const,
        position: { x: column * 230, y: row * 230 + offset * 100 },
        data: {
          label: node.type,
          status: liveStatus,
          agentExecutionId: node.agent_execution_id,
          decisionId: node.decision_id,
        },
      };
    });
  }, [graph, agentExecutionStatuses, runStatuses, runId]);

  const edges = useMemo<Edge[]>(() => {
    if (!graph) return [];
    return graph.edges.map((edge) => ({
      id: `${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      style: { stroke: "#333333" },
    }));
  }, [graph]);

  if (isLoading) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
        [LOADING GRAPH...]
      </div>
    );
  }
  if (isError || !graph) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-accent">[ERROR LOADING GRAPH]</div>
    );
  }

  return (
    <div style={{ height: 480 }} className="border border-border" data-testid="execution-graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        fitView
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node: GraphNodeType) => {
          const { agentExecutionId, decisionId } = node.data;
          if (agentExecutionId) {
            openInspector(agentExecutionId);
          } else if (decisionId) {
            openDecision(decisionId);
          }
        }}
      >
        <Background color="#222222" gap={16} />
      </ReactFlow>
    </div>
  );
}
