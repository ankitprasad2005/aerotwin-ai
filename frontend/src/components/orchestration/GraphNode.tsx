import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { GraphNodeContent } from "./GraphNodeContent";

export type GraphNodeType = Node<{ label: string; status: string }, "graphNode">;

export function GraphNode({ data }: NodeProps<GraphNodeType>) {
  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-border-visible" />
      <GraphNodeContent label={data.label} status={data.status} />
      <Handle type="source" position={Position.Bottom} className="!bg-border-visible" />
    </>
  );
}
