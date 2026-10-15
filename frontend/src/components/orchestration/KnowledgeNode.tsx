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
  DECISION: "border-ok text-ok",
  ROUTE: "border-line-strong text-ink",
  AIRCRAFT: "border-warn text-warn",
  CONSTRAINT: "border-line-strong text-muted",
};

export function KnowledgeNode({ data }: NodeProps<KnowledgeFlowNode>) {
  const style = TYPE_STYLE[data.nodeType] ?? "border-line-strong text-muted";

  return (
    <>
      <Handle type="target" position={Position.Left} className="!bg-line-strong" />
      <div
        className={`w-44 border bg-panel px-sm py-xs ${style}`}
        data-testid="knowledge-node"
      >
        <div className="label">{data.nodeType}</div>
        <div className="truncate font-mono text-sm text-ink" title={data.label}>
          {data.label}
        </div>
        {data.detail && (
          <div className="truncate font-mono text-[11px] text-faint" title={data.detail}>
            {data.detail}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-line-strong" />
    </>
  );
}
