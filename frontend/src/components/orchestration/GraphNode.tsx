import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { GraphNodeContent } from "./GraphNodeContent";

export type GraphNodeType = Node<
  { label: string; status: string; agentExecutionId?: string; decisionId?: string },
  "graphNode"
>;

export function GraphNode({ data }: NodeProps<GraphNodeType>) {
  return (
    <>
      <Handle type="target" position={Position.Left} className="!bg-line-strong" />
      <GraphNodeContent label={data.label} status={data.status} />
      <Handle type="source" position={Position.Right} className="!bg-line-strong" />
    </>
  );
}
