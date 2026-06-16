import type { GraphColumnRow, GraphEdge, GraphNode } from './types/lineage';
import type { GraphLike } from './graphPipeline';

export const COLUMN_CONTAINER = {
  filterThreshold: 30,
  hardRenderLimit: 120,
};

export interface BuildRelationColumnProjectionOptions {
  collapsedRelationIds: Record<string, true>;
  selectedEntityId?: string | null;
  searchTerm?: string;
  columnFilterThreshold?: number;
}

export function parsePhysicalColumnOwner(columnEntityId: string): { ownerEntityId: string; columnName: string } | null {
  const prefix = 'physical_column:';
  if (!columnEntityId.startsWith(prefix)) return null;

  const qualified = columnEntityId.slice(prefix.length);
  const lastDot = qualified.lastIndexOf('.');
  if (lastDot <= 0 || lastDot === qualified.length - 1) return null;

  return {
    ownerEntityId: `physical_table:${qualified.slice(0, lastDot)}`,
    columnName: qualified.slice(lastDot + 1),
  };
}

function sortColumns(columns: GraphColumnRow[]) {
  columns.sort((a, b) => {
    if (typeof a.ordinal === 'number' && typeof b.ordinal === 'number' && a.ordinal !== b.ordinal) {
      return a.ordinal - b.ordinal;
    }
    if (typeof a.ordinal === 'number' && typeof b.ordinal !== 'number') return -1;
    if (typeof a.ordinal !== 'number' && typeof b.ordinal === 'number') return 1;
    return a.label.localeCompare(b.label) || a.entityId.localeCompare(b.entityId);
  });
}

function sourceColumnRow(node: GraphNode, ownerEntityId: string): GraphColumnRow {
  const owner = parsePhysicalColumnOwner(node.entityId);
  return {
    entityId: node.entityId,
    label: owner?.columnName ?? node.label,
    ownerEntityId,
    role: 'source',
    ordinal: node.ordinal,
  };
}

function outputColumnRow(node: GraphNode, ownerEntityId: string): GraphColumnRow {
  return {
    entityId: node.entityId,
    label: node.label,
    ownerEntityId,
    role: 'output',
    ordinal: node.ordinal,
  };
}

function syntheticTable(ownerEntityId: string): GraphNode {
  const label = ownerEntityId.slice('physical_table:'.length).split('.').pop() || ownerEntityId;
  return {
    id: ownerEntityId,
    entityId: ownerEntityId,
    type: 'table',
    label,
    tag: 'TBL',
    x: 0,
    y: 0,
    columns: [],
  };
}

function resolveOutputOwner(base: GraphLike, outputFieldId: string): string | null {
  const direct = base.edges.find((edge) => edge.source === outputFieldId && edge.type === 'output');
  if (direct) return direct.target;
  return base.nodes.find((node) => node.type === 'output')?.entityId ?? null;
}

function markConnected(containers: Map<string, GraphNode>, edge: GraphEdge) {
  for (const [ownerId, portId] of [[edge.source, edge.sourcePort], [edge.target, edge.targetPort]] as const) {
    if (!portId) continue;
    const column = containers.get(ownerId)?.columns?.find((row) => row.entityId === portId);
    if (column) column.connected = true;
  }
}

function shouldKeepColumn(column: GraphColumnRow, options: BuildRelationColumnProjectionOptions, search: string) {
  if (column.connected) return true;
  if (options.selectedEntityId === column.entityId) return true;
  if (search && (`${column.label} ${column.entityId}`).toLowerCase().includes(search)) return true;
  if (column.warning) return true;
  return false;
}

function finalizeContainerColumns(node: GraphNode, options: BuildRelationColumnProjectionOptions): GraphNode {
  const allColumns = [...(node.columns ?? [])];
  sortColumns(allColumns);

  const threshold = options.columnFilterThreshold ?? COLUMN_CONTAINER.filterThreshold;
  const search = (options.searchTerm ?? '').trim().toLowerCase();
  let columns = allColumns;
  let hiddenColumnCount = 0;

  if (allColumns.length > threshold) {
    columns = allColumns.filter((column) => shouldKeepColumn(column, options, search));
    if (columns.length === 0) columns = allColumns.slice(0, Math.min(threshold, COLUMN_CONTAINER.hardRenderLimit));
    columns = columns.slice(0, COLUMN_CONTAINER.hardRenderLimit);
    hiddenColumnCount = Math.max(0, allColumns.length - columns.length);
  }

  return { ...node, columns, hiddenColumnCount };
}

function portOwner(columnOwnerById: Map<string, string>, id: string) {
  return columnOwnerById.get(id) ?? id;
}

function projectEdge(edge: GraphEdge, columnOwnerById: Map<string, string>, containerById: Map<string, GraphNode>): GraphEdge | null {
  const sourceOwner = portOwner(columnOwnerById, edge.source);
  const targetOwner = portOwner(columnOwnerById, edge.target);
  const sourceIsColumn = columnOwnerById.has(edge.source);
  const targetIsColumn = columnOwnerById.has(edge.target);

  if (!containerById.has(sourceOwner) && !containerById.has(targetOwner)) return null;

  return {
    ...edge,
    id: sourceIsColumn || targetIsColumn ? `column:${edge.id}` : edge.id,
    source: sourceOwner,
    target: targetOwner,
    sourcePort: sourceIsColumn ? edge.source : undefined,
    targetPort: targetIsColumn ? edge.target : undefined,
    originalSourceEntityId: sourceIsColumn ? edge.source : edge.originalSourceEntityId,
    originalTargetEntityId: targetIsColumn ? edge.target : edge.originalTargetEntityId,
  };
}

function degradeIfCollapsed(edge: GraphEdge, sourceNode?: GraphNode, targetNode?: GraphNode): GraphEdge {
  if (!sourceNode?.collapsed && !targetNode?.collapsed) return edge;
  return {
    ...edge,
    id: `collapsed:${edge.source}->${edge.target}:${edge.type}`,
    sourcePort: undefined,
    targetPort: undefined,
    originalSourceEntityId: edge.originalSourceEntityId ?? edge.sourcePort,
    originalTargetEntityId: edge.originalTargetEntityId ?? edge.targetPort,
    synthetic: true,
  };
}

function dedupeEdges(edges: GraphEdge[]) {
  const seen = new Set<string>();
  const result: GraphEdge[] = [];
  for (const edge of edges) {
    const collapsed = !edge.sourcePort && !edge.targetPort;
    const key = collapsed
      ? `${edge.source}->${edge.target}:${edge.type}`
      : `${edge.source}:${edge.sourcePort ?? '__node__'}->${edge.target}:${edge.targetPort ?? '__node__'}:${edge.type}:${edge.mapping ?? edge.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(edge);
  }
  return result;
}

export function buildRelationColumnProjection(base: GraphLike, options: BuildRelationColumnProjectionOptions): GraphLike {
  const containerById = new Map<string, GraphNode>();
  const columnOwnerById = new Map<string, string>();

  for (const node of base.nodes) {
    if (node.type === 'table' || node.type === 'output') {
      containerById.set(node.entityId, {
        ...node,
        columns: [],
        collapsed: Boolean(options.collapsedRelationIds[node.entityId]),
      });
    }
  }

  for (const node of base.nodes) {
    if (node.type !== 'column') continue;
    const owner = parsePhysicalColumnOwner(node.entityId);
    if (!owner) continue;
    if (!containerById.has(owner.ownerEntityId)) containerById.set(owner.ownerEntityId, syntheticTable(owner.ownerEntityId));
    containerById.get(owner.ownerEntityId)!.columns!.push(sourceColumnRow(node, owner.ownerEntityId));
    columnOwnerById.set(node.entityId, owner.ownerEntityId);
  }

  for (const node of base.nodes) {
    if (node.type !== 'output_field') continue;
    const ownerId = resolveOutputOwner(base, node.entityId);
    if (!ownerId || !containerById.has(ownerId)) continue;
    containerById.get(ownerId)!.columns!.push(outputColumnRow(node, ownerId));
    columnOwnerById.set(node.entityId, ownerId);
  }

  if (columnOwnerById.size === 0) {
    return { nodes: [], edges: [] };
  }

  const rawProjected = base.edges
    .map((edge) => projectEdge(edge, columnOwnerById, containerById))
    .filter((edge): edge is GraphEdge => Boolean(edge))
    .filter((edge) => edge.source !== edge.target || edge.sourcePort !== edge.targetPort);

  const degraded = rawProjected.map((edge) => degradeIfCollapsed(edge, containerById.get(edge.source), containerById.get(edge.target)));
  const projectedEdges = dedupeEdges(degraded);
  projectedEdges.forEach((edge) => markConnected(containerById, edge));

  const containers = Array.from(containerById.values()).map((node) => finalizeContainerColumns(node, options));
  const expressionNodes = base.nodes.filter((node) => node.type === 'expression' || node.type === 'unknown');
  const nodeIds = new Set([...containers, ...expressionNodes].map((node) => node.entityId));

  return {
    nodes: [...containers, ...expressionNodes],
    edges: projectedEdges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)),
  };
}
