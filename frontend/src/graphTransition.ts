import type { GraphEdge, GraphLike, GraphNode, Point, PositionMap, TransitionNodeSets } from './types/lineage';

export function nodeKey(node: GraphNode): string {
  return node.entityId || node.id;
}

export function graphPositions(graph: GraphLike): PositionMap {
  return Object.fromEntries(
    graph.nodes.map((node: GraphNode) => [
      nodeKey(node),
      { x: node.x ?? 0, y: node.y ?? 0 },
    ]),
  );
}

export function classifyTransitionNodes(
  previousGraph: GraphLike,
  nextGraph: GraphLike,
): TransitionNodeSets {
  const previousIds = new Set(previousGraph.nodes.map(nodeKey));
  const nextIds = new Set(nextGraph.nodes.map(nodeKey));

  return {
    persisting: [...nextIds].filter((id): id is string => previousIds.has(id)),
    entering: [...nextIds].filter((id): id is string => !previousIds.has(id)),
    exiting: [...previousIds].filter((id): id is string => !nextIds.has(id)),
  };
}

export function resolveEnterPosition(
  entityId: string,
  nextGraph: GraphLike,
  currentPositions: PositionMap,
): Point {
  const incoming = nextGraph.edges
    .filter((edge: GraphEdge) => edge.target === entityId)
    .map((edge: GraphEdge) => edge.source);

  for (const sourceId of incoming) {
    if (currentPositions[sourceId]) {
      return currentPositions[sourceId];
    }
  }

  const outgoing = nextGraph.edges
    .filter((edge: GraphEdge) => edge.source === entityId)
    .map((edge: GraphEdge) => edge.target);

  for (const targetId of outgoing) {
    if (currentPositions[targetId]) {
      return currentPositions[targetId];
    }
  }

  const node = nextGraph.nodes.find((item: GraphNode) => nodeKey(item) === entityId);

  return {
    x: (node?.x ?? 0) - 36,
    y: node?.y ?? 0,
  };
}

export function resolveExitPosition(
  entityId: string,
  previousGraph: GraphLike,
  targetPositions: PositionMap,
  currentPositions: PositionMap,
): Point {
  const outgoing = previousGraph.edges
    .filter((edge: GraphEdge) => edge.source === entityId)
    .map((edge: GraphEdge) => edge.target);

  for (const targetId of outgoing) {
    if (targetPositions[targetId]) {
      return targetPositions[targetId];
    }
  }

  const incoming = previousGraph.edges
    .filter((edge: GraphEdge) => edge.target === entityId)
    .map((edge: GraphEdge) => edge.source);

  for (const sourceId of incoming) {
    if (targetPositions[sourceId]) {
      return targetPositions[sourceId];
    }
  }

  return currentPositions[entityId] ?? { x: 0, y: 0 };
}

export interface GraphTransitionPlan {
  previousGraph: GraphLike;
  nextGraph: GraphLike;
  renderGraph: GraphLike;
  fromPositions: PositionMap;
  toPositions: PositionMap;
  enteringEntityIds: Set<string>;
  persistingEntityIds: Set<string>;
  exitingEntityIds: Set<string>;
  durationMs: number;
}

export interface CreateGraphTransitionPlanOptions {
  previousGraph: GraphLike;
  nextGraph: GraphLike;
  durationMs?: number;
}

export function createGraphTransitionPlan(
  options: CreateGraphTransitionPlanOptions,
): GraphTransitionPlan {
  const { previousGraph, nextGraph, durationMs = 260 } = options;

  const currentPositions = graphPositions(previousGraph);
  const targetPositions = graphPositions(nextGraph);

  const nodeSets = classifyTransitionNodes(previousGraph, nextGraph);

  const fromPositions: PositionMap = {};
  const toPositions: PositionMap = {};

  for (const entityId of nodeSets.persisting) {
    fromPositions[entityId] = currentPositions[entityId] ?? targetPositions[entityId];
    toPositions[entityId] = targetPositions[entityId];
  }

  for (const entityId of nodeSets.entering) {
    const enterFrom = resolveEnterPosition(entityId, nextGraph, currentPositions);
    fromPositions[entityId] = enterFrom;
    toPositions[entityId] = targetPositions[entityId];
  }

  for (const entityId of nodeSets.exiting) {
    fromPositions[entityId] = currentPositions[entityId];
    const exitTo = resolveExitPosition(entityId, previousGraph, targetPositions, currentPositions);
    toPositions[entityId] = exitTo;
  }

  const renderGraph = buildRenderGraph(previousGraph, nextGraph, nodeSets);

  return {
    previousGraph,
    nextGraph,
    renderGraph,
    fromPositions,
    toPositions,
    enteringEntityIds: new Set(nodeSets.entering),
    persistingEntityIds: new Set(nodeSets.persisting),
    exitingEntityIds: new Set(nodeSets.exiting),
    durationMs,
  };
}

function buildRenderGraph(
  previousGraph: GraphLike,
  nextGraph: GraphLike,
  nodeSets: TransitionNodeSets,
): GraphLike {
  const nodeMap = new Map<string, GraphNode>();
  const edgeMap = new Map<string, GraphEdge>();

  for (const node of previousGraph.nodes) {
    nodeMap.set(nodeKey(node), node);
  }

  for (const node of nextGraph.nodes) {
    nodeMap.set(nodeKey(node), node);
  }

  for (const edge of previousGraph.edges) {
    edgeMap.set(edge.id, edge);
  }

  for (const edge of nextGraph.edges) {
    edgeMap.set(edge.id, edge);
  }

  return {
    nodes: Array.from(nodeMap.values()),
    edges: Array.from(edgeMap.values()),
  };
}
export function interpolatePoint(
  from: Point,
  to: Point,
  progress: number,
): Point {
  return {
    x: from.x + (to.x - from.x) * progress,
    y: from.y + (to.y - from.y) * progress,
  };
}

export function interpolatePositions(
  fromPositions: PositionMap,
  toPositions: PositionMap,
  progress: number,
): PositionMap {
  const result: PositionMap = {};
  const ids = new Set([
    ...Object.keys(fromPositions),
    ...Object.keys(toPositions),
  ]);

  for (const id of ids) {
    const from = fromPositions[id] ?? toPositions[id];
    const to = toPositions[id] ?? fromPositions[id];

    if (!from || !to) {
      continue;
    }

    result[id] = interpolatePoint(from, to, progress);
  }

  return result;
}

export function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

export function shouldAnimateGraph(graph: GraphLike): boolean {
  if (typeof window !== 'undefined' && window.matchMedia) {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduceMotion) {
      return false;
    }
  }

  return (
    graph.nodes.length <= 120 &&
    graph.edges.length <= 220
  );
}

export function assertStableGraphEntityIds(graph: GraphLike): void {
  const seen = new Set<string>();

  for (const node of graph.nodes) {
    const id = nodeKey(node);

    if (!id) {
      throw new Error('Graph node is missing stable entity id');
    }

    if (seen.has(id)) {
      throw new Error(`Duplicate graph entity id: ${id}`);
    }

    seen.add(id);
  }
}

export function applyFramePositions(
  graph: GraphLike,
  positions: PositionMap,
): GraphLike {
  return {
    ...graph,
    nodes: graph.nodes.map((node: GraphNode) => {
      const position = positions[nodeKey(node)];

      if (!position) {
        return node;
      }

      return {
        ...node,
        x: position.x,
        y: position.y,
      };
    }),
  };
}

export function createImmediateGraphFrame(nextGraph: GraphLike): {
  graph: GraphLike;
  positions: PositionMap;
  progress: number;
  enteringEntityIds: Set<string>;
  exitingEntityIds: Set<string>;
} {
  return {
    graph: nextGraph,
    positions: graphPositions(nextGraph),
    progress: 1,
    enteringEntityIds: new Set(),
    exitingEntityIds: new Set(),
  };
}
