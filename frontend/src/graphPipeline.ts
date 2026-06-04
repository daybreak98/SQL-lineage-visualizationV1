import type { BackendAnalysisResult, GraphEdge, GraphNode, SearchItem, WorkbenchState } from './types/lineage';

// ============================================================
// 工具类型
// ============================================================

type RawApiNode = NonNullable<NonNullable<BackendAnalysisResult['graph_view_model']>['nodes']>[number];
type RawApiEdge = NonNullable<NonNullable<BackendAnalysisResult['graph_view_model']>['edges']>[number];

// ============================================================
// 辅助函数
// ============================================================

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

// ============================================================
// P0-1: ID归一化 —— node.id/entity_id → canonicalEntityId
// ============================================================

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
    };

    if (nodeEntityIds.has(source) && nodeEntityIds.has(target)) {
      validEdges.push(normalizedEdge);
    } else {
      invalidEdges.push(normalizedEdge);
    }
  });

  return { nodes, edges: validEdges, invalidEdges };
}

// ============================================================
// P0-1: 补齐 terminal → output 边
// ============================================================

export function ensureTerminalOutputEdges(graph: {
  nodes: GraphNode[];
  edges: GraphEdge[];
}): { nodes: GraphNode[]; edges: GraphEdge[] } {
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
      x: 0,
      y: 0,
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
    if (structureIds.has(e.source) && structureIds.has(e.target)) {
      structureSourcesWithOutgoing.add(e.source);
    }
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
      });
    }
  });

  return { nodes, edges };
}

// ============================================================
// P1-1: 分层 DAG 布局
// ============================================================

const LAYOUT = {
  startX: 80,
  startY: 72,
  rankGap: 230,
  nodeGap: 76,
};

function nodeTypeRankSeed(node: GraphNode): number {
  if (node.type === 'table' || node.type === 'column') return 0;
  if (node.type === 'cte') return 1;
  if (node.type === 'subquery' || node.type === 'expression') return 2;
  if (node.type === 'output' || node.type === 'output_field') return 99;
  return 1;
}

function orderNodesWithinLevels(
  nodes: GraphNode[],
  edges: GraphEdge[],
  levels: Map<string, number>,
): Map<number, GraphNode[]> {
  const levelMap = new Map<number, GraphNode[]>();
  for (const node of nodes) {
    const level = levels.get(node.entityId) ?? 0;
    if (!levelMap.has(level)) levelMap.set(level, []);
    levelMap.get(level)!.push(node);
  }

  const incoming = new Map<string, string[]>();
  const outgoing = new Map<string, string[]>();
  nodes.forEach((n) => {
    incoming.set(n.entityId, []);
    outgoing.set(n.entityId, []);
  });
  edges.forEach((e) => {
    incoming.get(e.target)?.push(e.source);
    outgoing.get(e.source)?.push(e.target);
  });

  const maxLevel = Math.max(...Array.from(levelMap.keys()));

  function indexMapForLevel(level: number) {
    const map = new Map<string, number>();
    const list = levelMap.get(level) || [];
    list.forEach((n, i) => map.set(n.entityId, i));
    return map;
  }

  function barycenter(ids: string[], neighborIndex: Map<string, number>) {
    const values = ids
      .map((id) => neighborIndex.get(id))
      .filter((v): v is number => v !== undefined);
    if (!values.length) return Number.POSITIVE_INFINITY;
    return values.reduce((sum, v) => sum + v, 0) / values.length;
  }

  for (let pass = 0; pass < 4; pass++) {
    for (let level = 1; level <= maxLevel; level++) {
      const prevIndex = indexMapForLevel(level - 1);
      const list = levelMap.get(level) || [];
      list.sort(
        (a, b) =>
          barycenter(incoming.get(a.entityId) || [], prevIndex) -
          barycenter(incoming.get(b.entityId) || [], prevIndex),
      );
    }
    for (let level = maxLevel - 1; level >= 0; level--) {
      const nextIndex = indexMapForLevel(level + 1);
      const list = levelMap.get(level) || [];
      list.sort(
        (a, b) =>
          barycenter(outgoing.get(a.entityId) || [], nextIndex) -
          barycenter(outgoing.get(b.entityId) || [], nextIndex),
      );
    }
  }

  return levelMap;
}

function alignOutputNodes(nodes: GraphNode[], edges: GraphEdge[]) {
  const nodeById = new Map(nodes.map((n) => [n.entityId, n]));
  const outputNodes = nodes.filter((n) => n.type === 'output' || n.type === 'output_field');

  for (const output of outputNodes) {
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

export function layoutLayeredDag(graph: {
  nodes: GraphNode[];
  edges: GraphEdge[];
}): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes = graph.nodes.map((n) => ({ ...n }));
  const { edges } = graph;
  const nodeById = new Map(nodes.map((n) => [n.entityId, n]));

  const incoming = new Map<string, string[]>();
  nodes.forEach((n) => {
    incoming.set(n.entityId, []);
  });

  edges.forEach((e) => {
    if (!nodeById.has(e.source) || !nodeById.has(e.target)) return;
    incoming.get(e.target)?.push(e.source);
  });

  const levels = new Map<string, number>();

  nodes.forEach((n) => {
    if (n.type === 'table' || n.type === 'column') {
      levels.set(n.entityId, 0);
    }
  });

  let changed = true;
  let guard = 0;
  while (changed && guard < nodes.length * 3) {
    changed = false;
    guard++;
    for (const node of nodes) {
      if (levels.has(node.entityId)) continue;
      if (node.type === 'output' || node.type === 'output_field') continue;
      const srcs = incoming.get(node.entityId) || [];
      if (srcs.length === 0) {
        levels.set(node.entityId, nodeTypeRankSeed(node));
        changed = true;
        continue;
      }
      const srcLevels = srcs.map((s) => levels.get(s)).filter((v): v is number => v !== undefined);
      if (srcLevels.length === srcs.length) {
        levels.set(node.entityId, Math.max(...srcLevels) + 1);
        changed = true;
      }
    }
  }

  for (const node of nodes) {
    if (!levels.has(node.entityId) && node.type !== 'output' && node.type !== 'output_field') {
      levels.set(node.entityId, nodeTypeRankSeed(node));
    }
  }

  const maxNonOutputLevel = Math.max(
    0,
    ...nodes
      .filter((n) => n.type !== 'output' && n.type !== 'output_field')
      .map((n) => levels.get(n.entityId) ?? 0),
  );

  nodes.forEach((n) => {
    if (n.type === 'output' || n.type === 'output_field') {
      levels.set(n.entityId, maxNonOutputLevel + 1);
    }
  });

  const orderedLevels = orderNodesWithinLevels(nodes, edges, levels);

  for (const [level, levelNodes] of orderedLevels.entries()) {
    levelNodes.forEach((n, index) => {
      n.x = LAYOUT.startX + level * LAYOUT.rankGap;
      n.y = LAYOUT.startY + index * LAYOUT.nodeGap;
    });
  }

  alignOutputNodes(nodes, edges);

  return { nodes, edges };
}

// ============================================================
// P1-2: 多端口边路由
// ============================================================

function nodeBox(type: GraphNode['type']) {
  if (type === 'output') return { width: 132, height: 32 };
  if (type === 'subquery') return { width: 138, height: 32 };
  if (type === 'cte' || type === 'output_field' || type === 'expression') return { width: 125, height: 30 };
  if (type === 'column') return { width: 122, height: 29 };
  return { width: 118, height: 29 };
}

function portOffset(index: number, count: number, gap = 9) {
  if (count <= 1) return 0;
  return (index - (count - 1) / 2) * gap;
}

export function buildPortIndexes(
  graph: { nodes: GraphNode[]; edges: GraphEdge[] },
  positions: Record<string, { x: number; y: number }>,
) {
  const nodeById = new Map(graph.nodes.map((n) => [n.entityId, n]));
  const outgoing = new Map<string, GraphEdge[]>();
  const incoming = new Map<string, GraphEdge[]>();

  for (const edge of graph.edges) {
    if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) continue;
    if (!outgoing.has(edge.source)) outgoing.set(edge.source, []);
    if (!incoming.has(edge.target)) incoming.set(edge.target, []);
    outgoing.get(edge.source)!.push(edge);
    incoming.get(edge.target)!.push(edge);
  }

  function nodeY(entityId: string) {
    const node = nodeById.get(entityId);
    if (!node) return 0;
    const p = positions[node.id] ?? { x: node.x, y: node.y };
    return p.y;
  }

  for (const list of outgoing.values()) {
    list.sort((a, b) => nodeY(a.target) - nodeY(b.target));
  }
  for (const list of incoming.values()) {
    list.sort((a, b) => nodeY(a.source) - nodeY(b.source));
  }

  const sourcePortIndex = new Map<string, number>();
  const sourcePortCount = new Map<string, number>();
  const targetPortIndex = new Map<string, number>();
  const targetPortCount = new Map<string, number>();

  for (const [source, list] of outgoing.entries()) {
    sourcePortCount.set(source, list.length);
    list.forEach((edge, i) => sourcePortIndex.set(edge.id, i));
  }
  for (const [target, list] of incoming.entries()) {
    targetPortCount.set(target, list.length);
    list.forEach((edge, i) => targetPortIndex.set(edge.id, i));
  }

  return { sourcePortIndex, sourcePortCount, targetPortIndex, targetPortCount };
}

export function routeEdgePath(params: {
  edge: GraphEdge;
  sourceNode: GraphNode;
  targetNode: GraphNode;
  sourcePos: { x: number; y: number };
  targetPos: { x: number; y: number };
  ports: ReturnType<typeof buildPortIndexes>;
}) {
  const { edge, sourceNode, targetNode, sourcePos, targetPos, ports } = params;
  const sourceBox = nodeBox(sourceNode.type);
  const targetBox = nodeBox(targetNode.type);

  const sourceCount = ports.sourcePortCount.get(edge.source) ?? 1;
  const sourceIndex = ports.sourcePortIndex.get(edge.id) ?? 0;
  const targetCount = ports.targetPortCount.get(edge.target) ?? 1;
  const targetIndex = ports.targetPortIndex.get(edge.id) ?? 0;

  const sx = sourcePos.x + sourceBox.width;
  const sy = sourcePos.y + sourceBox.height / 2 + portOffset(sourceIndex, sourceCount);
  const tx = targetPos.x;
  const ty = targetPos.y + targetBox.height / 2 + portOffset(targetIndex, targetCount);
  const dx = tx - sx;

  if (dx >= 120) {
    const midX = sx + dx * 0.5;
    const bend = Math.min(80, Math.max(32, dx * 0.25));
    return [
      `M ${sx} ${sy}`,
      `C ${sx + bend} ${sy}, ${midX - bend} ${sy}, ${midX} ${sy}`,
      `L ${midX} ${ty}`,
      `C ${midX + bend} ${ty}, ${tx - bend} ${ty}, ${tx} ${ty}`,
    ].join(' ');
  }

  const loopX = Math.max(sx, tx) + 96;
  const bend = 42;
  return [
    `M ${sx} ${sy}`,
    `C ${sx + bend} ${sy}, ${loopX} ${sy}, ${loopX} ${(sy + ty) / 2}`,
    `C ${loopX} ${ty}, ${tx - bend} ${ty}, ${tx} ${ty}`,
  ].join(' ');
}

// ============================================================
// 辅助：colToTables + searchItems
// ============================================================

function buildColToTablesByEdges(graph: {
  nodes: GraphNode[];
  edges: GraphEdge[];
}): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  for (const edge of graph.edges) {
    result[edge.target] = result[edge.target] || [];
    if (!result[edge.target].includes(edge.source)) {
      result[edge.target].push(edge.source);
    }
  }
  return result;
}

function buildSearchItems(
  result: BackendAnalysisResult,
  graph: { nodes: GraphNode[]; edges: GraphEdge[] },
  colToTables: Record<string, string[]>,
): SearchItem[] {
  const outputNodes = graph.nodes.filter(
    (n) => n.type === 'output' || n.type === 'output_field',
  );
  const sourceNodes = graph.nodes.filter(
    (n) => n.type === 'table' || n.type === 'column' || n.type === 'cte' || n.type === 'subquery',
  );

  return [
    ...outputNodes.map((node, index) => {
      const sources = colToTables[node.entityId] || [];
      return {
        itemId: `search-output-${index}`,
        entityId: node.entityId,
        displayName: node.label,
        type: 'output' as const,
        sub: sources.length ? `from: ${sources.join(', ')}` : 'unknown source',
        reason: sources.length ? 'lineage edge' : '无法确认字段来源',
        confidence: (sources.length ? 'high' : result.status === 'partial' ? 'medium' : 'low') as 'high' | 'medium' | 'low',
        warning: !sources.length,
      };
    }),
    ...sourceNodes.map((node, index) => ({
      itemId: `search-source-${index}`,
      entityId: node.entityId,
      displayName: node.label,
      type: (node.type === 'cte' || node.type === 'subquery' ? 'subquery' : 'source') as 'subquery' | 'source',
      sub: node.type,
      reason: 'backend graph',
      confidence: 'high' as const,
    })),
  ];
}

// ============================================================
// 编排：新 analysisToGraph
// ============================================================

export function analysisToGraph(result: BackendAnalysisResult): {
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  searchItems: SearchItem[];
  colToTables: Record<string, string[]>;
  invalidEdges: GraphEdge[];
} {
  const normalized = normalizeBackendGraph(result);
  const withOutput = ensureTerminalOutputEdges({
    nodes: normalized.nodes,
    edges: normalized.edges,
  });
  const layouted = layoutLayeredDag(withOutput);
  const colToTables = buildColToTablesByEdges(layouted);
  const searchItems = buildSearchItems(result, layouted, colToTables);

  return {
    graph: layouted,
    searchItems,
    colToTables,
    invalidEdges: normalized.invalidEdges,
  };
}

// ============================================================
// P0-2: 新 visibleGraph —— 只过滤 + 合成边，不硬编码坐标
// ============================================================

export function visibleGraph(state: WorkbenchState): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const gvm = state.graphViewMode ?? 'table';
  if (!state.backendGraph) return { nodes: [], edges: [] };

  const base = state.backendGraph;
  const mergePositions = (nodes: GraphNode[]) =>
    nodes.map((n) => {
      const saved = state.positions[n.id];
      return saved ? { ...n, x: saved.x, y: saved.y } : n;
    });

  if (gvm === 'subquery') {
    const allowedTypes = new Set<GraphNode['type']>(['table', 'cte', 'subquery', 'output']);
    const filteredNodes = base.nodes.filter((n) => allowedTypes.has(n.type));
    const ids = new Set(filteredNodes.map((n) => n.entityId));
    const filteredEdges = base.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    return layoutLayeredDag({ nodes: mergePositions(filteredNodes), edges: filteredEdges });
  }

  if (gvm === 'table') {
    return visibleTableGraph(base, state.positions);
  }

  if (gvm === 'column') {
    const allowedTypes = new Set<GraphNode['type']>(['column', 'output_field', 'expression', 'unknown']);
    const filteredNodes = base.nodes.filter((n) => allowedTypes.has(n.type));
    const ids = new Set(filteredNodes.map((n) => n.entityId));
    const filteredEdges = base.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    return layoutLayeredDag({ nodes: mergePositions(filteredNodes), edges: filteredEdges });
  }

  if (gvm === 'semantics' || gvm === 'expression' || gvm === 'diagnostics') {
    return base;
  }

  if (['subquery_dependency', 'large_graph', 'full_graph_preview'].includes(state.renderMode)) {
    return base;
  }

  return { nodes: [], edges: [] };
}

function visibleTableGraph(
  base: { nodes: GraphNode[]; edges: GraphEdge[] },
  positions: Record<string, { x: number; y: number }>,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes = base.nodes.filter((n) => n.type === 'table' || n.type === 'output');
  const ids = new Set(nodes.map((n) => n.entityId));
  const existingEdges = base.edges.filter((e) => ids.has(e.source) && ids.has(e.target));

  const output = nodes.find((n) => n.type === 'output');
  const tableNodes = nodes.filter((n) => n.type === 'table');
  const synthesizedEdges: GraphEdge[] = [];

  if (output) {
    for (const table of tableNodes) {
      if (!existingEdges.some((e) => e.source === table.entityId && e.target === output.entityId)) {
        synthesizedEdges.push({
          id: `table-view:${table.entityId}->${output.entityId}`,
          source: table.entityId,
          target: output.entityId,
          type: 'table',
          mapping: 'table_view_synthetic',
        });
      }
    }
  }

  const mergePositions = (ns: GraphNode[]) =>
    ns.map((n) => {
      const saved = positions[n.id];
      return saved ? { ...n, x: saved.x, y: saved.y } : n;
    });

  return layoutLayeredDag({
    nodes: mergePositions(nodes),
    edges: [...existingEdges, ...synthesizedEdges],
  });
}
