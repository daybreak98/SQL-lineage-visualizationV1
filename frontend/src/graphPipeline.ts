import type { BackendAnalysisResult, GraphEdge, GraphNode, SearchItem, WorkbenchState } from './types/lineage';
import { getComfortNodeBox, COMFORT_CANVAS } from './nodeVisualTokens';
import {
  applyManualPositions as applyComfortManualPositions,
  layoutComfortGraph,
  buildComfortPortIndexes,
  routeComfortEdgePath,
  type ComfortGraph,
  type ManualPositions,
} from './graphComfortLayout';


type RawApiNode = NonNullable<NonNullable<BackendAnalysisResult['graph_view_model']>['nodes']>[number];
type RawApiEdge = NonNullable<NonNullable<BackendAnalysisResult['graph_view_model']>['edges']>[number];

export type GraphLike = { nodes: GraphNode[]; edges: GraphEdge[] };
export type PositionMap = Record<string, { x: number; y: number }>;


const LAYOUT = {
  startX: 80,
  startY: 72,
  rankGap: 230,
  nodeGap: 76,
  columnNodeGap: 64,
  portGap: 10,
  tableGroupThreshold: 8,
};


function rawNodeType(node: RawApiNode): string {
  return node.node_type || node.type || '';
}

function rawNodeId(node: RawApiNode, index: number): string {
  return node.id || node.entity_id || `api-node-${index}`;
}

function canonicalEntityId(node: RawApiNode, index: number): string {
  return node.entity_id || node.id || `api-node-${index}`;
}

function normalizeEdgeType(type?: string): GraphEdge['type'] {
  if (type === 'column_lineage') return 'projection';
  if (type === 'output_column_to_result') return 'output';
  if (type === 'table_to_result') return 'table';
  if (type === 'table_to_cte') return 'table';
  if (type === 'cte_dependency') return 'cte';
  if (type === 'cte_to_result') return 'output';
  if (type === 'subquery_to_result') return 'subq';
  if (type === 'subquery_dependency') return 'subq';
  if (type === 'projection') return 'projection';
  if (type === 'alias') return 'alias';
  if (type === 'unknown') return 'unknown';
  if (type === 'cte') return 'cte';
  if (type === 'subq' || type === 'subquery') return 'subq';
  if (type === 'expr' || type === 'expression') return 'expr';
  if (type === 'join') return 'join';
  if (type === 'output') return 'output';
  return 'table';
}

function normalizeNodeType(type?: string): GraphNode['type'] {
  if (type === 'table') return 'table';
  if (type === 'column' || type === 'physical_column') return 'column';
  if (type === 'cte') return 'cte';
  if (type === 'subquery') return 'subquery';
  if (type === 'output') return 'output';
  if (type === 'output_column' || type === 'output_field') return 'output_field';
  if (type === 'expression') return 'expression';
  if (type === 'unknown') return 'unknown';
  return 'unknown';
}

function tagForNodeType(type?: string) {
  if (type === 'output_column' || type === 'output_field' || type === 'output') return 'OUT';
  if (type === 'column' || type === 'physical_column') return 'COL';
  if (type === 'table') return 'TBL';
  if (type === 'cte') return 'CTE';
  if (type === 'subquery') return 'SUBQ';
  if (type === 'expression') return 'EXPR';
  if (type === 'unknown') return '?';
  return undefined;
}

function isStructureNode(node: GraphNode) {
  return node.type === 'table' || node.type === 'cte' || node.type === 'subquery';
}

export function nodeBox(type: GraphNode['type']) {
  const box = getComfortNodeBox(type);
  return { width: box.width, height: box.height };
}


function buildNodeRefMap(apiNodes: RawApiNode[]) {
  const refToEntity = new Map<string, string>();
  apiNodes.forEach((node, index) => {
    const entityId = canonicalEntityId(node, index);
    const rid = rawNodeId(node, index);
    if (rid) refToEntity.set(rid, entityId);
    if (node.id) refToEntity.set(node.id, entityId);
    if (node.entity_id) refToEntity.set(node.entity_id, entityId);
  });
  return refToEntity;
}

function resolveGraphRef(ref: string | undefined, refToEntity: Map<string, string>) {
  if (!ref) return '';
  return refToEntity.get(ref) || ref;
}

export function normalizeBackendGraph(result: BackendAnalysisResult): {
  nodes: GraphNode[];
  edges: GraphEdge[];
  invalidEdges: GraphEdge[];
} {
  const apiNodes = result.graph_view_model?.nodes || [];
  const apiEdges = result.graph_view_model?.edges || [];
  const refToEntity = buildNodeRefMap(apiNodes);

  const nodes: GraphNode[] = apiNodes.map((node, index) => {
    const rawType = rawNodeType(node);
    const entityId = canonicalEntityId(node, index);
    const id = rawNodeId(node, index);
    const label = node.label || node.name || entityId;
    const nodeType = normalizeNodeType(rawType);

    return {
      id,
      entityId,
      type: nodeType,
      label: nodeType === 'table' ? label.split('.').pop() || label : label,
      tag: tagForNodeType(rawType),
      x: node.position?.x ?? node.x ?? 0,
      y: node.position?.y ?? node.y ?? 0,
      rank: typeof node.rank === 'number' ? node.rank : undefined,
      lane: typeof node.lane === 'string' ? node.lane : undefined,
      semanticRole: typeof node.semantic_role === 'string' ? node.semantic_role : undefined,
      orderInRank: typeof node.order_in_rank === 'number' ? node.order_in_rank : undefined,
    };
  });

  const nodeEntityIds = new Set(nodes.map((n) => n.entityId));
  const validEdges: GraphEdge[] = [];
  const invalidEdges: GraphEdge[] = [];

  apiEdges.forEach((edge, index) => {
    const source = resolveGraphRef(edge.source, refToEntity);
    const target = resolveGraphRef(edge.target, refToEntity);

    const normalizedEdge: GraphEdge = {
      id: edge.id || `api-edge-${index}`,
      source,
      target,
      type: normalizeEdgeType(edge.edge_type || edge.type),
      mapping: edge.mapping || edge.id || `${source}->${target}`,
      sourcePortOrder: typeof edge.source_port_order === 'number' ? edge.source_port_order : undefined,
      targetPortOrder: typeof edge.target_port_order === 'number' ? edge.target_port_order : undefined,
    };

    if (nodeEntityIds.has(source) && nodeEntityIds.has(target)) {
      validEdges.push(normalizedEdge);
    } else {
      invalidEdges.push(normalizedEdge);
    }
  });

  return { nodes, edges: validEdges, invalidEdges };
}


export function ensureTerminalOutputEdges(graph: GraphLike): GraphLike {
  const nodes = [...graph.nodes];
  const edges = [...graph.edges];

  let outputNode = nodes.find((n) => n.type === 'output');

  if (!outputNode) {
    outputNode = {
      id: 'api-query-result',
      entityId: 'out:query_result',
      type: 'output',
      label: 'Query Result',
      tag: 'OUT',
      x: 0, y: 0,
    };
    nodes.push(outputNode);
  }

  const outputId = outputNode.entityId;
  const structureNodes = nodes.filter(isStructureNode);
  const structureIds = new Set(structureNodes.map((n) => n.entityId));
  const hasIncomingToOutput = edges.some((e) => e.target === outputId);

  if (hasIncomingToOutput) return { nodes, edges };

  const structureSourcesWithOutgoing = new Set<string>();
  edges.forEach((e) => {
    if (structureIds.has(e.source) && structureIds.has(e.target))
      structureSourcesWithOutgoing.add(e.source);
  });

  const terminalNodes = structureNodes.filter(
    (n) => !structureSourcesWithOutgoing.has(n.entityId),
  );
  const fallbackTerminals = terminalNodes.length > 0 ? terminalNodes : structureNodes;

  fallbackTerminals.forEach((node) => {
    const edgeId = `synthetic:${node.entityId}->${outputId}`;
    if (!edges.some((e) => e.source === node.entityId && e.target === outputId)) {
      edges.push({
        id: edgeId,
        source: node.entityId,
        target: outputId,
        type: node.type === 'subquery' ? 'subq' : node.type === 'cte' ? 'cte' : 'table',
        mapping: 'synthetic_terminal_output',
        synthetic: true,
      });
    }
  });

  return { nodes, edges };
}


function nodeTypeRankSeed(node: GraphNode): number {
  if (node.type === 'table' || node.type === 'column') return 0;
  if (node.type === 'cte') return 1;
  if (node.type === 'subquery' || node.type === 'expression') return 2;
  if (node.type === 'output' || node.type === 'output_field') return 99;
  return 1;
}

function orderNodesWithinLevels(
  nodes: GraphNode[], edges: GraphEdge[], levels: Map<string, number>,
): Map<number, GraphNode[]> {
  const levelMap = new Map<number, GraphNode[]>();
  for (const node of nodes) {
    const level = levels.get(node.entityId) ?? 0;
    if (!levelMap.has(level)) levelMap.set(level, []);
    levelMap.get(level)!.push(node);
  }

  const incoming = new Map<string, string[]>();
  const outgoing = new Map<string, string[]>();
  nodes.forEach((n) => { incoming.set(n.entityId, []); outgoing.set(n.entityId, []); });
  edges.forEach((e) => {
    incoming.get(e.target)?.push(e.source);
    outgoing.get(e.source)?.push(e.target);
  });

  const maxLevel = Math.max(...Array.from(levelMap.keys()), 0);

  function indexMapForLevel(level: number) {
    const map = new Map<string, number>();
    (levelMap.get(level) || []).forEach((n, i) => map.set(n.entityId, i));
    return map;
  }

  function barycenter(ids: string[], neighborIndex: Map<string, number>) {
    const values = ids.map((id) => neighborIndex.get(id)).filter((v): v is number => v !== undefined);
    if (!values.length) return Number.POSITIVE_INFINITY;
    return values.reduce((sum, v) => sum + v, 0) / values.length;
  }

  for (let pass = 0; pass < 4; pass++) {
    for (let level = 1; level <= maxLevel; level++) {
      const prevIndex = indexMapForLevel(level - 1);
      (levelMap.get(level) || []).sort(
        (a, b) => barycenter(incoming.get(a.entityId) || [], prevIndex)
                - barycenter(incoming.get(b.entityId) || [], prevIndex),
      );
    }
    for (let level = maxLevel - 1; level >= 0; level--) {
      const nextIndex = indexMapForLevel(level + 1);
      (levelMap.get(level) || []).sort(
        (a, b) => barycenter(outgoing.get(a.entityId) || [], nextIndex)
                - barycenter(outgoing.get(b.entityId) || [], nextIndex),
      );
    }
  }
  return levelMap;
}

function alignOutputNodes(nodes: GraphNode[], edges: GraphEdge[]) {
  const nodeById = new Map(nodes.map((n) => [n.entityId, n]));

  for (const output of nodes.filter((n) => n.type === 'output')) {
    const parents = edges
      .filter((e) => e.target === output.entityId)
      .map((e) => nodeById.get(e.source))
      .filter((n): n is GraphNode => Boolean(n));
    if (!parents.length) continue;
    const sortedY = parents.map((n) => n.y).sort((a, b) => a - b);
    const mid = Math.floor(sortedY.length / 2);
    output.y = sortedY.length % 2 === 1 ? sortedY[mid] : (sortedY[mid - 1] + sortedY[mid]) / 2;
  }
}

function resolveNodeCollisionsByRank(nodes: GraphNode[], minGap = LAYOUT.nodeGap) {
  const rankGroups = new Map<number, GraphNode[]>();

  for (const node of nodes) {
    const rank = Math.round(node.x);
    if (!rankGroups.has(rank)) rankGroups.set(rank, []);
    rankGroups.get(rank)!.push(node);
  }

  for (const group of rankGroups.values()) {
    if (group.length <= 1) continue;
    group.sort((a, b) => a.y - b.y);

    for (let i = 1; i < group.length; i++) {
      const prev = group[i - 1];
      const curr = group[i];
      if (curr.y - prev.y < minGap) {
        curr.y = prev.y + minGap;
      }
    }

    const top = group[0]?.y ?? 0;
    const delta = top - LAYOUT.startY;
    if (delta > 0) {
      for (const node of group) node.y -= delta * 0.35;
    }
  }
}

export function layoutLayeredDag(graph: GraphLike): GraphLike {
  const result = layoutComfortGraph(graph);
  return { nodes: result.nodes, edges: result.edges };
}


export function applyManualPositions(graph: GraphLike, positions: PositionMap): GraphLike {
  return applyComfortManualPositions(graph, positions);
}


function portOffset(index: number, count: number, gap = LAYOUT.portGap) {
  if (count <= 1) return 0;
  return (index - (count - 1) / 2) * gap;
}

export function buildPortIndexes(graph: GraphLike, positions: PositionMap) {
  return buildComfortPortIndexes(graph);
}

export function routeEdgePath(params: {
  edge: GraphEdge;
  sourceNode: GraphNode;
  targetNode: GraphNode;
  sourcePos: { x: number; y: number };
  targetPos: { x: number; y: number };
  ports: ReturnType<typeof buildPortIndexes>;
  style?: 'smooth' | 'orthogonal';
}) {
  const { edge, sourceNode, targetNode, sourcePos, targetPos, ports } = params;
  const s = { ...sourceNode, x: sourcePos.x, y: sourcePos.y };
  const t = { ...targetNode, x: targetPos.x, y: targetPos.y };
  return routeComfortEdgePath({ edge, sourceNode: s, targetNode: t, ports });
}


function buildColToTablesByEdges(graph: GraphLike): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  for (const edge of graph.edges) {
    result[edge.target] = result[edge.target] || [];
    if (!result[edge.target].includes(edge.source)) result[edge.target].push(edge.source);
  }
  return result;
}

function buildSearchItems(
  result: BackendAnalysisResult,
  graph: GraphLike,
  colToTables: Record<string, string[]>,
): SearchItem[] {
  const outputNodes = graph.nodes.filter((n) => n.type === 'output' || n.type === 'output_field');
  const sourceNodes = graph.nodes.filter(
    (n) => n.type === 'table' || n.type === 'column' || n.type === 'cte' || n.type === 'subquery',
  );
  return [
    ...outputNodes.map((node, index) => {
      const sources = colToTables[node.entityId] || [];
      return {
        itemId: `search-output-${index}`, entityId: node.entityId, displayName: node.label,
        type: 'output' as const,
        sub: sources.length ? `from: ${sources.join(', ')}` : 'unknown source',
        reason: sources.length ? 'lineage edge' : '鏃犳硶纭瀛楁鏉ユ簮',
        confidence: (sources.length ? 'high' : result.status === 'partial' ? 'medium' : 'low') as 'high' | 'medium' | 'low',
        warning: !sources.length,
      };
    }),
    ...sourceNodes.map((node, index) => ({
      itemId: `search-source-${index}`, entityId: node.entityId, displayName: node.label,
      type: (node.type === 'cte' || node.type === 'subquery' ? 'subquery' : 'source') as 'subquery' | 'source',
      sub: node.type, reason: 'backend graph', confidence: 'high' as const,
    })),
  ];
}


export function analysisToGraph(result: BackendAnalysisResult): {
  graph: GraphLike;
  searchItems: SearchItem[];
  colToTables: Record<string, string[]>;
  invalidEdges: GraphEdge[];
} {
  const normalized = normalizeBackendGraph(result);
  const withOutput = ensureTerminalOutputEdges({ nodes: normalized.nodes, edges: normalized.edges });
  const colToTables = buildColToTablesByEdges(withOutput);
  const searchItems = buildSearchItems(result, withOutput, colToTables);
  return { graph: withOutput, searchItems, colToTables, invalidEdges: normalized.invalidEdges };
}


function findAncestorsOfTarget(edges: GraphEdge[], targetId: string): Set<string> {
  const reverse = new Map<string, string[]>();
  for (const edge of edges) {
    if (!reverse.has(edge.target)) reverse.set(edge.target, []);
    reverse.get(edge.target)!.push(edge.source);
  }

  const ancestors = new Set<string>();
  const queue = [...(reverse.get(targetId) || [])];
  while (queue.length) {
    const current = queue.shift()!;
    if (ancestors.has(current)) continue;
    ancestors.add(current);
    for (const parent of reverse.get(current) || []) queue.push(parent);
  }
  return ancestors;
}

function visibleTableGraph(
  base: GraphLike,
  positions: PositionMap,
): GraphLike {
  const output = base.nodes.find((n) => n.type === 'output');
  if (!output) {
    const nodes = base.nodes.filter((n) => n.type === 'table');
    return applyManualPositions(layoutLayeredDag({ nodes, edges: [] }), positions);
  }

  const ancestors = findAncestorsOfTarget(base.edges, output.entityId);
  let tableNodes = base.nodes.filter((n) => n.type === 'table' && ancestors.has(n.entityId));
  if (!tableNodes.length) tableNodes = base.nodes.filter((n) => n.type === 'table');

  if (tableNodes.length > LAYOUT.tableGroupThreshold) {
    return visibleGroupedTableGraph(tableNodes, output, positions);
  }

  const nodes = [...tableNodes, output];
  const ids = new Set(nodes.map((n) => n.entityId));
  const existingEdges = base.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  const synthesizedEdges: GraphEdge[] = [];

  for (const table of tableNodes) {
    if (!existingEdges.some((e) => e.source === table.entityId && e.target === output.entityId)) {
      synthesizedEdges.push({
        id: `table-view:${table.entityId}->${output.entityId}`,
        source: table.entityId,
        target: output.entityId,
        type: 'table',
        mapping: 'table_view_synthetic',
        synthetic: true,
      });
    }
  }

  const layouted = layoutLayeredDag({ nodes, edges: [...existingEdges, ...synthesizedEdges] });
  return applyManualPositions(layouted, positions);
}

function visibleGroupedTableGraph(
  tableNodes: GraphNode[],
  output: GraphNode,
  positions: PositionMap,
): GraphLike {
  const sourceGroupNode: GraphNode = {
    id: 'virtual-source-group',
    entityId: 'virtual:source_tables',
    type: 'subquery',
    label: `Source Tables (${tableNodes.length})`,
    tag: 'SRC',
    x: 0, y: 0,
  };

  const edges: GraphEdge[] = [
    ...tableNodes.map((table) => ({
      id: `table-group:${table.entityId}`,
      source: table.entityId,
      target: sourceGroupNode.entityId,
      type: 'table' as const,
      mapping: 'table_view_grouped',
      synthetic: true,
    })),
    {
      id: `group-output:${sourceGroupNode.entityId}->${output.entityId}`,
      source: sourceGroupNode.entityId,
      target: output.entityId,
      type: 'output' as const,
      mapping: 'table_view_grouped_output',
      synthetic: true,
    },
  ];

  const layouted = layoutLayeredDag({ nodes: [...tableNodes, sourceGroupNode, output], edges });
  return applyManualPositions(layouted, positions);
}


function visibleSubqueryGraph(base: GraphLike, positions: PositionMap): GraphLike {
  const allowedTypes = new Set<GraphNode['type']>(['table', 'cte', 'subquery', 'output']);
  const nodes = base.nodes.filter((n) => allowedTypes.has(n.type));
  const ids = new Set(nodes.map((n) => n.entityId));
  const edges = base.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  const layouted = layoutLayeredDag({ nodes, edges });
  return applyManualPositions(layouted, positions);
}


function layoutColumnLineage(graph: GraphLike): GraphLike {
  const nodes = graph.nodes.map((n) => ({ ...n }));
  const { edges } = graph;
  const sourceX = LAYOUT.startX;
  const expressionX = LAYOUT.startX + 170;
  const outputFieldX = LAYOUT.startX + 290;
  const resultX = outputFieldX + 320;

  const outputFields = nodes
    .filter((n) => n.type === 'output_field')
    .sort((a, b) => {
      const ao = a.ordinal;
      const bo = b.ordinal;
      if (typeof ao === 'number' && typeof bo === 'number') return ao - bo;
      return a.label.localeCompare(b.label);
    });

  const outputIndex = new Map<string, number>();
  outputFields.forEach((node, index) => {
    node.x = outputFieldX;
    node.y = LAYOUT.startY + index * LAYOUT.columnNodeGap;
    outputIndex.set(node.entityId, index);
  });

  const resultNodes = nodes.filter((n) => n.type === 'output');
  const outputYValues = outputFields.map((node) => node.y);
  const resultY = outputYValues.length
    ? outputYValues.reduce((sum, y) => sum + y, 0) / outputYValues.length
    : LAYOUT.startY;
  resultNodes.forEach((node) => {
    node.x = resultX;
    node.y = resultY;
  });

  const sourceNodes = nodes.filter((n) => n.type !== 'output_field' && n.type !== 'output');
  sourceNodes.forEach((source, sourceOrder) => {
    const targetIndexes = edges
      .filter((e) => e.source === source.entityId)
      .map((e) => outputIndex.get(e.target))
      .filter((v): v is number => v !== undefined);

    const avgTargetIndex = targetIndexes.length
      ? targetIndexes.reduce((sum, v) => sum + v, 0) / targetIndexes.length
      : sourceOrder;

    if (source.type === 'expression') {
      source.x = expressionX;
    } else {
      source.x = sourceX;
    }

    source.y = LAYOUT.startY + avgTargetIndex * LAYOUT.columnNodeGap;
  });

  resolveNodeCollisionsByRank(nodes, 58);
  return { nodes, edges };
}

function visibleColumnGraph(base: GraphLike, positions: PositionMap): GraphLike {
  const hasOutputFields = base.nodes.some((n) => n.type === 'output_field');
  if (!hasOutputFields) return { nodes: [], edges: [] };

  const baseNodeById = new Map(base.nodes.map((node) => [node.entityId, node]));
  const visibleNodeById = new Map<string, GraphNode>();
  const visibleEdges: GraphEdge[] = [];
  const seenEdges = new Set<string>();

  const addVisibleNode = (node: GraphNode) => {
    if (!visibleNodeById.has(node.entityId)) visibleNodeById.set(node.entityId, { ...node });
  };

  const addVisibleEdge = (edge: GraphEdge) => {
    const key = `${edge.source}->${edge.target}:${edge.type}`;
    if (seenEdges.has(key)) return;
    visibleEdges.push({ ...edge, id: edge.id || key });
    seenEdges.add(key);
  };

  const tableNodeFromColumn = (columnId: string): GraphNode | null => {
    if (!columnId.startsWith('physical_column:')) return null;
    const sourceLabel = columnId.slice('physical_column:'.length);
    const lastDot = sourceLabel.lastIndexOf('.');
    if (lastDot <= 0) return null;
    const tableName = sourceLabel.slice(0, lastDot);
    const tableId = `physical_table:${tableName}`;
    const existing = baseNodeById.get(tableId);
    if (existing) return existing;
    return {
      id: tableId,
      entityId: tableId,
      type: 'table',
      label: tableName.split('.').pop() || tableName,
      tag: 'TBL',
      x: 0,
      y: 0,
    };
  };

  base.nodes.forEach((node) => {
    if (node.type === 'output_field' || node.type === 'output' || node.type === 'expression' || node.type === 'unknown') {
      addVisibleNode(node);
    }
  });

  base.edges.forEach((edge) => {
    const target = baseNodeById.get(edge.target);
    if (edge.type === 'projection' && target?.type === 'output_field') {
      const source = baseNodeById.get(edge.source);
      if (source?.type === 'column') {
        const tableNode = tableNodeFromColumn(source.entityId);
        if (!tableNode) return;
        addVisibleNode(tableNode);
        addVisibleNode(target);
        addVisibleEdge({
          ...edge,
          id: `collapsed:${tableNode.entityId}->${target.entityId}:${edge.id}`,
          source: tableNode.entityId,
          target: target.entityId,
        });
        return;
      }
    }

    if (edge.type === 'output') {
      const source = baseNodeById.get(edge.source);
      const output = baseNodeById.get(edge.target);
      if (source?.type === 'output_field' && output?.type === 'output') {
        addVisibleNode(source);
        addVisibleNode(output);
        addVisibleEdge(edge);
      }
    }
  });

  const nodes = Array.from(visibleNodeById.values());
  const ids = new Set(nodes.map((n) => n.entityId));
  const edges = visibleEdges.filter((e) => ids.has(e.source) && ids.has(e.target));
  const layouted = layoutColumnLineage({ nodes, edges });
  return applyManualPositions(layouted, positions);
}


export function visibleGraph(state: WorkbenchState): GraphLike {
  const base = state.backendGraph;
  if (!base) return { nodes: [], edges: [] };

  const positions = state.positions || {};
  const mode = state.graphViewMode ?? 'table';

  if (mode === 'table') return visibleTableGraph(base, positions);
  if (mode === 'subquery') return visibleSubqueryGraph(base, positions);
  if (mode === 'column') return visibleColumnGraph(base, positions);

  // semantics / diagnostics / expression / fallback — apply layout too
  return applyManualPositions(layoutLayeredDag(base), positions);
}
