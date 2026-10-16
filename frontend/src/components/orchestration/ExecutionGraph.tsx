import { useMemo } from "react";
import { Background, ReactFlow, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useRunGraph } from "../../api/useRuns";
import { useDecisionInspectorStore } from "../../stores/decisionInspectorStore";
import { useEventStreamStore } from "../../stores/eventStreamStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import { GraphNode, type GraphNodeType } from "./GraphNode";
import { layoutGraph } from "./graphLayout";

const NODE_TYPES = { graphNode: GraphNode };

const TERMINAL_STATUSES = new Set(["COMPLETED", "FAILED"]);

export function ExecutionGraph({ runId }: { runId: string }) {
  const { data: graph, isLoading, isError } = useRunGraph(runId);
  const agentExecutionStatuses = useEventStreamStore((state) => state.agentExecutionStatuses);
  const runStatuses = useEventStreamStore((state) => state.runStatuses);
  const openInspector = useInspectorStore((state) => state.open);
  const openDecision = useDecisionInspectorStore((state) => state.open);

  const nodes = useMemo<GraphNodeType[]>(() => {
    if (!graph) return [];
    const positions = layoutGraph(graph.nodes, graph.edges);
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
      return {
        id: node.id,
        type: "graphNode" as const,
        position: positions.get(node.id) as { x: number; y: number },
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
      type: "smoothstep",
      style: { stroke: "#2d3748" },
    }));
  }, [graph]);

  if (isLoading) {
    return (
      <div className="label text-faint">
        [LOADING GRAPH...]
      </div>
    );
  }
  if (isError || !graph) {
    return (
      <div className="label text-bad">[ERROR LOADING GRAPH]</div>
    );
  }

  return (
    <div style={{ height: 480 }} className="border border-line" data-testid="execution-graph">
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
        <Background color="#1f2733" gap={16} />
      </ReactFlow>
    </div>
  );
}
