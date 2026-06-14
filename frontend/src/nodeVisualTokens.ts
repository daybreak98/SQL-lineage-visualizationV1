export type GraphNodeType =
  | 'table'
  | 'column'
  | 'cte'
  | 'subquery'
  | 'expression'
  | 'output'
  | 'output_field'
  | 'unknown';

export const COMFORT_CANVAS = {
  minWidth: 1420,
  minHeight: 680,
  marginX: 90,
  marginY: 64,
  minRankGap: 210,
  minNodeGap: 86,
};

export const COMFORT_NODE_BOX: Record<string, { width: number; height: number; radius: number }> = {
  table: { width: 207, height: 45, radius: 12 },
  column: { width: 138, height: 45, radius: 12 },
  cte: { width: 110, height: 45, radius: 12 },
  subquery: { width: 110, height: 45, radius: 12 },
  expression: { width: 138, height: 45, radius: 12 },
  output: { width: 138, height: 45, radius: 12 },
  output_field: { width: 138, height: 45, radius: 12 },
  unknown: { width: 138, height: 45, radius: 12 },
};

export const COMFORT_EDGE = {
  strokeWidth: 1.7,
  activeStrokeWidth: 2.8,
  opacity: 0.72,
  dimOpacity: 0.12,
  activeOpacity: 1,
};

export function getComfortNodeBox(type: string) {
  return COMFORT_NODE_BOX[type] ?? COMFORT_NODE_BOX.unknown;
}

export function nodeBoxComfort(type: string): { width: number; height: number } {
  const box = getComfortNodeBox(type);
  return { width: box.width, height: box.height };
}

export type NodeGeometry = {
  node: { id: string; entityId: string; type: string; x: number; y: number };
  box: { width: number; height: number };
  cx: number;
  cy: number;
  left: number;
  right: number;
  top: number;
  bottom: number;
};

export function buildNodeGeometryIndex(nodes: { id: string; entityId: string; type: string; x: number; y: number }[]) {
  const geometryByEntity = new Map<string, NodeGeometry>();
  for (const node of nodes) {
    const box = getComfortNodeBox(node.type);
    geometryByEntity.set(node.entityId, {
      node,
      box,
      cx: node.x,
      cy: node.y,
      left: node.x - box.width / 2,
      right: node.x + box.width / 2,
      top: node.y - box.height / 2,
      bottom: node.y + box.height / 2,
    });
  }
  return geometryByEntity;
}

export function clampPortOffset(offset: number, nodeType: string, margin = 10) {
  const box = getComfortNodeBox(nodeType);
  const maxOffset = Math.max(0, box.height / 2 - margin);
  return Math.max(-maxOffset, Math.min(maxOffset, offset));
}

export function validateRenderableGraph(params: {
  nodes: { entityId: string }[];
  edges: { id: string; source: string; target: string }[];
}) {
  const nodeIds = new Set(params.nodes.map((n) => n.entityId));
  const missingEdges: { id: string; source: string; target: string }[] = [];
  for (const edge of params.edges) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) missingEdges.push(edge);
  }
  return { nodeCount: params.nodes.length, edgeCount: params.edges.length, missingEndpointEdgeCount: missingEdges.length, missingEndpointEdges: missingEdges };
}
