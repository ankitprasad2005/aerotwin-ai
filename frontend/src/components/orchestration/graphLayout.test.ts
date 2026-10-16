import { describe, expect, it } from "vitest";
import { COLUMN_WIDTH, ROW_HEIGHT, layoutGraph, type LayoutEdge, type LayoutNode } from "./graphLayout";

function iterationNodes(n: number): { nodes: LayoutNode[]; edges: LayoutEdge[] } {
  const agents = ["NETWORK", "MAINTENANCE", "FLEET", "CREW", "CARGO", "WEATHER", "FINANCE", "EMISSIONS"];
  const nodes: LayoutNode[] = [
    { id: `ctx-${n}`, type: "CONTEXT_ENGINE", iteration: n },
    ...agents.map((a) => ({ id: `${a}-${n}`, type: `${a}_AGENT`, iteration: n })),
    { id: `dec-${n}`, type: "DECISION_ENGINE", iteration: n },
    { id: `fin-${n}`, type: "FINAL_DECISION", iteration: n },
  ];
  const edges: LayoutEdge[] = [
    ...agents.flatMap((a) => [
      { source: `ctx-${n}`, target: `${a}-${n}` },
      { source: `${a}-${n}`, target: `dec-${n}` },
    ]),
    { source: `dec-${n}`, target: `fin-${n}` },
  ];
  return { nodes, edges };
}

function overlaps(nodes: LayoutNode[], pos: Map<string, { x: number; y: number }>): boolean {
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = pos.get(nodes[i].id)!;
      const b = pos.get(nodes[j].id)!;
      if (a.x === b.x && Math.abs(a.y - b.y) < ROW_HEIGHT) return true;
    }
  }
  return false;
}

describe("layoutGraph", () => {
  it("places dependants to the right of their dependencies, strictly left to right", () => {
    const { nodes, edges } = iterationNodes(1);
    const pos = layoutGraph(nodes, edges);
    const x = (id: string) => pos.get(id)!.x;
    expect(x("FLEET-1")).toBeGreaterThan(x("NETWORK-1"));
    expect(x("FLEET-1")).toBeGreaterThan(x("MAINTENANCE-1"));
    expect(x("CREW-1")).toBeGreaterThan(x("NETWORK-1"));
    expect(x("NETWORK-1")).toBe(x("MAINTENANCE-1"));
    expect(x("dec-1")).toBeGreaterThan(x("FLEET-1"));
    expect(x("fin-1")).toBeGreaterThan(x("dec-1"));
    expect(x("ctx-1")).toBeLessThan(x("NETWORK-1"));
  });

  it("does not overlap nodes sharing a column and centres columns on the band", () => {
    const { nodes, edges } = iterationNodes(1);
    const pos = layoutGraph(nodes, edges);
    expect(overlaps(nodes, pos)).toBe(false);
    // 6 dependants is the tallest column; the single-node columns sit at its vertical centre.
    expect(pos.get("ctx-1")!.y).toBe((6 * ROW_HEIGHT - ROW_HEIGHT) / 2);
  });

  it("gives each iteration its own band below the previous one", () => {
    const one = iterationNodes(1);
    const two = iterationNodes(2);
    const nodes = [{ id: "orchestrator", type: "ORCHESTRATOR", iteration: null }, ...one.nodes, ...two.nodes];
    const edges = [
      { source: "orchestrator", target: "ctx-1" },
      ...one.edges,
      { source: "fin-1", target: "ctx-2" },
      ...two.edges,
    ];
    const pos = layoutGraph(nodes, edges);
    expect(overlaps(nodes, pos)).toBe(false);
    const ys = (n: number) => nodes.filter((v) => v.iteration === n).map((v) => pos.get(v.id)!.y);
    expect(Math.min(...ys(2))).toBeGreaterThan(Math.max(...ys(1)));
    expect(pos.get("orchestrator")!.x).toBeLessThan(pos.get("ctx-1")!.x);
    expect(pos.get("ctx-2")!.x).toBe(pos.get("ctx-1")!.x - COLUMN_WIDTH);
  });

  it("falls back to the stage columns when there are no edges", () => {
    const nodes: LayoutNode[] = [
      { id: "o", type: "ORCHESTRATOR" },
      { id: "a", type: "NETWORK_AGENT", iteration: 1 },
      { id: "f", type: "FINAL_DECISION", iteration: 1 },
    ];
    const pos = layoutGraph(nodes, []);
    expect(pos.get("o")!.x).toBe(0);
    expect(pos.get("a")!.x).toBe(2 * COLUMN_WIDTH);
    expect(pos.get("f")!.x).toBe(4 * COLUMN_WIDTH);
  });

  it("falls back to the stage columns when the edges contain a cycle", () => {
    const nodes: LayoutNode[] = [
      { id: "c", type: "CONTEXT_ENGINE", iteration: 1 },
      { id: "a", type: "NETWORK_AGENT", iteration: 1 },
    ];
    const pos = layoutGraph(nodes, [
      { source: "c", target: "a" },
      { source: "a", target: "c" },
    ]);
    expect(pos.get("c")!.x).toBe(COLUMN_WIDTH);
    expect(pos.get("a")!.x).toBe(2 * COLUMN_WIDTH);
  });

  it("handles an empty graph", () => {
    expect(layoutGraph([], []).size).toBe(0);
  });
});
