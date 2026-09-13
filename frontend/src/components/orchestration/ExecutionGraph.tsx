import { useMemo } from "react";
import { Background, ReactFlow, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useRunGraph } from "../../api/useRuns";
import { useEventStreamStore } from "../../stores/eventStreamStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import { GraphNode, type GraphNodeType } from "./GraphNode";

const NODE_TYPES = { graphNode: GraphNode };

function layoutPosition(index: number): { x: number; y: number } {
  return { x: (index % 4) * 220, y: Math.floor(index / 4) * 140 };
}

export function ExecutionGraph({ runId }: { runId: string }) {
  const { data: graph, isLoading, isError } = useRunGraph(runId);
  const agentExecutionStatuses = useEventStreamStore((state) => state.agentExecutionStatuses);
  const runStatuses = useEventStreamStore((state) => state.runStatuses);
  const openInspector = useInspectorStore((state) => state.open);

  const nodes = useMemo<GraphNodeType[]>(() => {
    if (!graph) return [];
    return graph.nodes.map((node, index) => {
      let liveStatus = node.status;
      if (node.agent_execution_id && agentExecutionStatuses[node.agent_execution_id]) {
        liveStatus = agentExecutionStatuses[node.agent_execution_id];
      } else if (node.type === "ORCHESTRATOR" && runStatuses[runId]) {
        liveStatus = runStatuses[runId];
      }
      return {
        id: node.id,
        type: "graphNode" as const,
        position: layoutPosition(index),
        data: { label: node.type, status: liveStatus, agentExecutionId: node.agent_execution_id },
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
          const { agentExecutionId } = node.data;
          if (agentExecutionId) openInspector(agentExecutionId);
        }}
      >
        <Background color="#222222" gap={16} />
      </ReactFlow>
    </div>
  );
}
