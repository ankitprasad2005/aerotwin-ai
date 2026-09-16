import { useMemo } from "react";
import { Background, ReactFlow, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useRunKnowledgeGraph } from "../../api/useRuns";
import { useDecisionInspectorStore } from "../../stores/decisionInspectorStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import { KnowledgeNode, type KnowledgeFlowNode } from "./KnowledgeNode";

const NODE_TYPES = { knowledgeNode: KnowledgeNode };

// Knowledge flows left to right — what the agents were given, then the agents, then what they
// produced — with one column per kind, stacked vertically. A single row per rank grew wider than
// React Flow's minimum zoom could fit, which cut nodes off the canvas.
const COLUMN: Record<string, number> = { CONSTRAINT: 0, ROUTE: 1, AIRCRAFT: 2, AGENT: 3, DECISION: 4 };

export function KnowledgeGraph({ runId }: { runId: string }) {
  const { data: graph, isLoading, isError } = useRunKnowledgeGraph(runId);
  const openInspector = useInspectorStore((state) => state.open);
  const openDecision = useDecisionInspectorStore((state) => state.open);

  const nodes = useMemo<KnowledgeFlowNode[]>(() => {
    if (!graph) return [];
    const usedRows = new Map<number, number>();
    return graph.nodes.map((node) => {
      const column = COLUMN[node.type] ?? 0;
      const row = usedRows.get(column) ?? 0;
      usedRows.set(column, row + 1);
      return {
        id: node.id,
        type: "knowledgeNode" as const,
        position: { x: column * 240, y: row * 90 },
        data: {
          label: node.label,
          detail: node.detail,
          nodeType: node.type,
          agentExecutionId: node.agent_execution_id,
          decisionId: node.decision_id,
        },
      };
    });
  }, [graph]);

  const edges = useMemo<Edge[]>(() => {
    if (!graph) return [];
    return graph.edges.map((edge) => ({
      id: `${edge.source}-${edge.target}-${edge.label}`,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      style: { stroke: "#333333" },
      labelStyle: { fill: "#999999", fontSize: 10, fontFamily: "Space Mono, monospace" },
      labelBgStyle: { fill: "#111111" },
    }));
  }, [graph]);

  if (isLoading) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
        [LOADING KNOWLEDGE GRAPH...]
      </div>
    );
  }
  if (isError || !graph) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-accent">
        [ERROR LOADING KNOWLEDGE GRAPH]
      </div>
    );
  }
  if (graph.nodes.length === 0) {
    return (
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-disabled">
        [NO AGENT KNOWLEDGE YET]
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-sm">
      <p className="text-body-sm text-text-secondary">
        What each agent knew: the twin entities in its context and the constraints it was given,
        plus what it recommended. Entities shared by several agents are one node, so the graph shows
        where their knowledge overlaps.
      </p>
      <div style={{ height: 520 }} className="border border-border" data-testid="knowledge-graph">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          fitView
          minZoom={0.2}
          proOptions={{ hideAttribution: true }}
          onNodeClick={(_, node: KnowledgeFlowNode) => {
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
    </div>
  );
}
