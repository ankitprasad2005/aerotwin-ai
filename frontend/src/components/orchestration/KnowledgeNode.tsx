import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import type { KnowledgeNodeType } from "../../types";

export type KnowledgeFlowNode = Node<
  {
    label: string;
    detail: string;
    nodeType: KnowledgeNodeType;
    agentExecutionId?: string;
    decisionId?: string;
  },
  "knowledgeNode"
>;

const TYPE_STYLE: Record<string, string> = {
  AGENT: "border-accent text-accent",
  DECISION: "border-success text-success",
  ROUTE: "border-interactive text-interactive",
  AIRCRAFT: "border-warning text-warning",
  CONSTRAINT: "border-border-visible text-text-secondary",
};

export function KnowledgeNode({ data }: NodeProps<KnowledgeFlowNode>) {
  const style = TYPE_STYLE[data.nodeType] ?? "border-border-visible text-text-secondary";

  return (
    <>
      <Handle type="target" position={Position.Left} className="!bg-border-visible" />
      <div
        className={`w-44 border bg-surface px-sm py-xs ${style}`}
        data-testid="knowledge-node"
      >
        <div className="font-mono text-[11px] uppercase tracking-[0.08em]">{data.nodeType}</div>
        <div className="truncate font-mono text-body-sm text-text-primary" title={data.label}>
          {data.label}
        </div>
        {data.detail && (
          <div className="truncate font-mono text-[11px] text-text-disabled" title={data.detail}>
            {data.detail}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-border-visible" />
    </>
  );
}
