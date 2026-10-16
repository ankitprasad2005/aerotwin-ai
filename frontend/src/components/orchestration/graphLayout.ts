// Strictly left-to-right layout for the execution graph. The column is the node's longest-path
// depth from the iteration's source nodes; each iteration (follow-up prompt) is its own
// horizontal band, sized to its tallest column, stacked below the previous one.

export interface LayoutNode {
  id: string;
  type: string;
  iteration?: number | null;
}
export interface LayoutEdge {
  source: string;
  target: string;
}

export const COLUMN_WIDTH = 240;
export const ROW_HEIGHT = 96;
export const BAND_GAP = 70;

// The backend only emits context -> agent -> decision edges, but some agents consume others'
// output. These layout-only dependencies (never drawn) put dependants one column to the right.
const AGENT_DEPENDENCIES: Record<string, string[]> = {
  FLEET_AGENT: ["NETWORK_AGENT", "MAINTENANCE_AGENT"],
  CREW_AGENT: ["NETWORK_AGENT"],
  CARGO_AGENT: ["NETWORK_AGENT"],
  WEATHER_AGENT: ["NETWORK_AGENT"],
  FINANCE_AGENT: ["NETWORK_AGENT"],
  EMISSIONS_AGENT: ["NETWORK_AGENT"],
};

const STAGE_COLUMN: Record<string, number> = {
  ORCHESTRATOR: 0,
  CONTEXT_ENGINE: 1,
  DECISION_ENGINE: 3,
  FINAL_DECISION: 4,
};

function stageColumn(type: string): number {
  return STAGE_COLUMN[type] ?? 2;
}

/** Longest-path depth per node id, or null if there are no edges or they contain a cycle. */
function depths(nodes: LayoutNode[], edges: LayoutEdge[]): Map<string, number> | null {
  if (edges.length === 0) return null;
  const incoming = new Map<string, number>(nodes.map((n) => [n.id, 0]));
  const outgoing = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) {
    incoming.set(e.target, (incoming.get(e.target) ?? 0) + 1);
    outgoing.get(e.source)?.push(e.target);
  }
  const depth = new Map<string, number>(nodes.map((n) => [n.id, 0]));
  const queue = nodes.filter((n) => incoming.get(n.id) === 0).map((n) => n.id);
  let visited = 0;
  while (queue.length > 0) {
    const id = queue.shift() as string;
    visited += 1;
    for (const next of outgoing.get(id) ?? []) {
      depth.set(next, Math.max(depth.get(next) ?? 0, (depth.get(id) ?? 0) + 1));
      incoming.set(next, (incoming.get(next) ?? 0) - 1);
      if (incoming.get(next) === 0) queue.push(next);
    }
  }
  return visited === nodes.length ? depth : null;
}

export function layoutGraph(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
): Map<string, { x: number; y: number }> {
  const iterations = nodes.map((n) => n.iteration).filter((i): i is number => typeof i === "number");
  const firstIteration = iterations.length > 0 ? Math.min(...iterations) : 1;

  const groups = new Map<number, LayoutNode[]>();
  for (const node of nodes) {
    const key = node.iteration ?? firstIteration;
    groups.set(key, [...(groups.get(key) ?? []), node]);
  }

  const positions = new Map<string, { x: number; y: number }>();
  let bandTop = 0;
  for (const key of [...groups.keys()].sort((a, b) => a - b)) {
    const members = groups.get(key) as LayoutNode[];
    const ids = new Set(members.map((n) => n.id));
    const groupEdges = edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    const byType = (type: string) => members.filter((n) => n.type === type);
    for (const [type, deps] of Object.entries(AGENT_DEPENDENCIES)) {
      for (const dependant of byType(type)) {
        for (const dep of deps.flatMap(byType)) {
          groupEdges.push({ source: dep.id, target: dependant.id });
        }
      }
    }
    const depth = depths(members, groupEdges);

    const columns = new Map<number, LayoutNode[]>();
    for (const node of members) {
      const column = depth ? (depth.get(node.id) as number) : stageColumn(node.type);
      columns.set(column, [...(columns.get(column) ?? []), node]);
    }
    const tallest = Math.max(...[...columns.values()].map((c) => c.length));
    const bandHeight = tallest * ROW_HEIGHT;
    for (const [column, columnNodes] of columns) {
      const top = bandTop + (bandHeight - columnNodes.length * ROW_HEIGHT) / 2;
      columnNodes.forEach((node, index) => {
        positions.set(node.id, { x: column * COLUMN_WIDTH, y: top + index * ROW_HEIGHT });
      });
    }
    bandTop += bandHeight + BAND_GAP;
  }
  return positions;
}
