// ============================================================
// Lineage Graph V2 — 血缘图画布核心代码（dsv4 实现版）
// 供超级前端工程师评审
// ============================================================
// 
// 文件清单：
//   §A  graphPipeline.ts          659行  新增  核心管道
//   §B  LineageCanvas.tsx         353行  修改  画布渲染+交互
//   §C  types/lineage.ts          相关类型（仅供参考）
//   §D  selectors.ts              viewHighlightSets/currentEntitySet（辅助）
//   §E  App.tsx onAnalyze()       管道接入点
//
// 与旧版对比：
//   旧版: analysisToGraph 混入 BFS+colToTables+searchItems (332行单体)
//         visibleGraph 硬编码 x=72/x=292 覆盖布局
//         边路由仅处理相同 source::target 对，偏移 16px
//         node.id / entity_id 混用导致边丢失
//         output 节点孤立无入边
//
//   新版: normalizeBackendGraph → ensureTerminalOutputEdges → layoutLayeredDag
//         visibleGraph 只过滤 + 合成边，统一走布局
//         边路由按端口分配 + midX lane + loop 回环
//         refToEntity 双向映射解决 ID 不一致
//         ensureTerminalOutputEdges 兜底 output 连接

// ============================================================
// §A  core: graphPipeline.ts  (完整 659 行)
// ============================================================
// 文件路径: frontend/src/graphPipeline.ts

import type { BackendAnalysisResult, GraphEdge, GraphNode, SearchItem, WorkbenchState } from './types/lineage';

// -- 工具类型 --
type RawApiNode = NonNullable<NonNullable<BackendAnalysisResult['graph_view_model']>['nodes']>[number];
type RawApiEdge = NonNullable<NonNullable<BackendAnalysisResult['graph_view_model']>['edges']>[number];

// -- 辅助函数 --
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
// A1. ID 归一化 —— 解决 edge.source/target 使用 node.id 但前端 byEntity 用 entityId 导致边丢失
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

/** ★ 入口：API 响应 → 归一化 Graph（validEdges + invalidEdges） */
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
// A2. 终端 output 边补齐 —— 解决 Query Result 节点孤立
// ============================================================

/** ★ 若 output 无入边，找 terminal structure nodes 补 synthetic 边 */
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
      x: 0, y: 0,
    };
    nodes.push(outputNode);
  }

  const outputId = outputNode.entityId;
  const structureNodes = nodes.filter(isStructureNode);
  const structureIds = new Set(structureNodes.map((n) => n.entityId));

  if (edges.some((e) => e.target === outputId)) return { nodes, edges };

  // 找出终端节点（没有继续指向其他结构节点的）
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
      });
    }
  });

  return { nodes, edges };
}

// ============================================================
// A3. 分层 DAG 布局 —— 替换旧版 BFS 手动布局
// ============================================================

const LAYOUT = { startX: 80, startY: 72, rankGap: 230, nodeGap: 76 };

function nodeTypeRankSeed(node: GraphNode): number {
  if (node.type === 'table' || node.type === 'column') return 0;
  if (node.type === 'cte') return 1;
  if (node.type === 'subquery' || node.type === 'expression') return 2;
  if (node.type === 'output' || node.type === 'output_field') return 99;
  return 1;
}

/** barycenter 排序：邻居节点位置均值，双向扫描 4 轮减少交叉 */
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

  const maxLevel = Math.max(...Array.from(levelMap.keys()));

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

/** output 节点 Y 对齐直接上游 medianY */
function alignOutputNodes(nodes: GraphNode[], edges: GraphEdge[]) {
  const nodeById = new Map(nodes.map((n) => [n.entityId, n]));
  for (const output of nodes.filter((n) => n.type === 'output' || n.type === 'output_field')) {
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

/** ★ 主布局入口 */
export function layoutLayeredDag(graph: {
  nodes: GraphNode[]; edges: GraphEdge[];
}): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes = graph.nodes.map((n) => ({ ...n }));
  const { edges } = graph;
  const nodeById = new Map(nodes.map((n) => [n.entityId, n]));

  const incoming = new Map<string, string[]>();
  nodes.forEach((n) => incoming.set(n.entityId, []));
  edges.forEach((e) => {
    if (!nodeById.has(e.source) || !nodeById.has(e.target)) return;
    incoming.get(e.target)?.push(e.source);
  });

  const levels = new Map<string, number>();
  nodes.forEach((n) => {
    if (n.type === 'table' || n.type === 'column') levels.set(n.entityId, 0);
  });

  let changed = true, guard = 0;
  while (changed && guard < nodes.length * 3) {
    changed = false; guard++;
    for (const node of nodes) {
      if (levels.has(node.entityId)) continue;
      if (node.type === 'output' || node.type === 'output_field') continue;
      const srcs = incoming.get(node.entityId) || [];
      if (srcs.length === 0) {
        levels.set(node.entityId, nodeTypeRankSeed(node)); changed = true; continue;
      }
      const srcLevels = srcs.map((s) => levels.get(s)).filter((v): v is number => v !== undefined);
      if (srcLevels.length === srcs.length) {
        levels.set(node.entityId, Math.max(...srcLevels) + 1); changed = true;
      }
    }
  }

  for (const node of nodes) {
    if (!levels.has(node.entityId) && node.type !== 'output' && node.type !== 'output_field')
      levels.set(node.entityId, nodeTypeRankSeed(node));
  }

  const maxNonOutputLevel = Math.max(0, ...nodes
    .filter((n) => n.type !== 'output' && n.type !== 'output_field')
    .map((n) => levels.get(n.entityId) ?? 0));

  nodes.forEach((n) => {
    if (n.type === 'output' || n.type === 'output_field')
      levels.set(n.entityId, maxNonOutputLevel + 1);
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
// A4. 多端口边路由 —— 替换旧版 source::target 分组偏移
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

/** ★ 为每个 source/target 的出入边分配端口索引（按对端Y排序） */
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
    return (positions[node.id] ?? { x: node.x, y: node.y }).y;
  }

  for (const list of outgoing.values()) list.sort((a, b) => nodeY(a.target) - nodeY(b.target));
  for (const list of incoming.values()) list.sort((a, b) => nodeY(a.source) - nodeY(b.source));

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

/** ★ SVG path 生成：长边用 midX lane，短边用外侧 loop */
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

  // 长边：midX lane（水平→垂直→水平）
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

  // 短边/回环：外侧绕过
  const loopX = Math.max(sx, tx) + 96;
  const bend = 42;
  return [
    `M ${sx} ${sy}`,
    `C ${sx + bend} ${sy}, ${loopX} ${sy}, ${loopX} ${(sy + ty) / 2}`,
    `C ${loopX} ${ty}, ${tx - bend} ${ty}, ${tx} ${ty}`,
  ].join(' ');
}

// ============================================================
// A5. colToTables + searchItems + 编排入口
// ============================================================

function buildColToTablesByEdges(graph: { nodes: GraphNode[]; edges: GraphEdge[] }): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  for (const edge of graph.edges) {
    result[edge.target] = result[edge.target] || [];
    if (!result[edge.target].includes(edge.source)) result[edge.target].push(edge.source);
  }
  return result;
}

function buildSearchItems(
  result: BackendAnalysisResult,
  graph: { nodes: GraphNode[]; edges: GraphEdge[] },
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
        reason: sources.length ? 'lineage edge' : '无法确认字段来源',
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

/** ★★★ 编排入口 */
export function analysisToGraph(result: BackendAnalysisResult): {
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  searchItems: SearchItem[];
  colToTables: Record<string, string[]>;
  invalidEdges: GraphEdge[];
} {
  const normalized = normalizeBackendGraph(result);
  const withOutput = ensureTerminalOutputEdges({ nodes: normalized.nodes, edges: normalized.edges });
  const layouted = layoutLayeredDag(withOutput);
  const colToTables = buildColToTablesByEdges(layouted);
  const searchItems = buildSearchItems(result, layouted, colToTables);
  return { graph: layouted, searchItems, colToTables, invalidEdges: normalized.invalidEdges };
}

// ============================================================
// A6. 新 visibleGraph —— 只过滤，不硬编码坐标
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

  if (gvm === 'table') return visibleTableGraph(base, state.positions);

  if (gvm === 'column') {
    const allowedTypes = new Set<GraphNode['type']>(['column', 'output_field', 'expression', 'unknown']);
    const filteredNodes = base.nodes.filter((n) => allowedTypes.has(n.type));
    const ids = new Set(filteredNodes.map((n) => n.entityId));
    const filteredEdges = base.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    return layoutLayeredDag({ nodes: mergePositions(filteredNodes), edges: filteredEdges });
  }

  if (gvm === 'semantics' || gvm === 'expression' || gvm === 'diagnostics') return base;
  if (['subquery_dependency', 'large_graph', 'full_graph_preview'].includes(state.renderMode)) return base;
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
  const synthesizedEdges: GraphEdge[] = [];
  if (output) {
    for (const table of nodes.filter((n) => n.type === 'table')) {
      if (!existingEdges.some((e) => e.source === table.entityId && e.target === output.entityId)) {
        synthesizedEdges.push({
          id: `table-view:${table.entityId}->${output.entityId}`,
          source: table.entityId, target: output.entityId, type: 'table', mapping: 'table_view_synthetic',
        });
      }
    }
  }
  return layoutLayeredDag({
    nodes: nodes.map((n) => { const saved = positions[n.id]; return saved ? { ...n, x: saved.x, y: saved.y } : n; }),
    edges: [...existingEdges, ...synthesizedEdges],
  });
}

// ============================================================
// §B  renderer: LineageCanvas.tsx 边渲染核心 (替换部分)
// ============================================================
// 文件路径: frontend/src/components/LineageCanvas.tsx
//
// 渲染中使用 graphPipeline 的 buildPortIndexes + routeEdgePath：
//
//   import { buildPortIndexes, routeEdgePath } from '../graphPipeline';
//
//   const ports = buildPortIndexes(graph, positions);
//   ...
//   const edgePath = routeEdgePath({ edge, sourceNode, targetNode, sourcePos, targetPos, ports });
//
// 画布结构 (不变)：
//   <div.viewport>                       ← 视口，ResizeObserver 监听
//     <div.canvas-transform>              ← translate(viewOffset)
//       <div.stage>                       ← scale(zoom)
//         <svg.edge-layer>                ← SVG 边层
//           { edges.map(edge => ...
//             <path d={edgePath} markerEnd={...} /> )}
//         </svg>
//         { nodes.map(node =>             ← DIV 节点层
//           <div.node style={{ left, top }} onMouseDown=拖拽 onClick=选中>
//             <span.strip/><span.title/></div> )}
//       </div>
//     </div>
//   </div>
//
// 交互逻辑 (不变)：
//   - 节点拖拽: onMouseDown → startDrag → applyPointer → setDraftPositions
//   - 画布平移: onMouseDown(空白) → startPan → applyPointer → setManualPan
//   - 缩放: onWheel → zoomBy → clamp(0.25~3)
//   - 双击定位: onDoubleClick → revealInEditor
//   - 边被覆层: <path.edge-hit> 透明宽线捕获点击
//
// 交互设计要点（两路鼠标监听）：
//   - 组件 onMouseMove → applyPointer 直接更新（保证手感）
//   - window mousemove → queuePointer → requestAnimationFrame（兜底快速甩出）

// ============================================================
// §C  types: 核心类型定义
// ============================================================
// 文件路径: frontend/src/types/lineage.ts

interface GraphNode {
  id: string;
  entityId: string;
  type: 'table' | 'column' | 'cte' | 'subquery' | 'output' | 'output_field' | 'expression' | 'unknown';
  label: string;
  tag?: string;
  x: number;
  y: number;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: 'table' | 'cte' | 'subq' | 'output' | 'expr' | 'join' | 'projection' | 'alias' | 'unknown';
  mapping?: string;
}

interface WorkbenchState {
  graphViewMode?: 'table' | 'subquery' | 'column' | 'expression' | 'semantics' | 'diagnostics';
  backendGraph?: { nodes: GraphNode[]; edges: GraphEdge[] };
  backendInvalidEdges?: GraphEdge[];   // ★ 新增
  positions: Record<string, { x: number; y: number }>;
  // ... 其他字段
}

// ============================================================
// §D  selectors: 辅助函数
// ============================================================
// 文件路径: frontend/src/data/selectors.ts
// visibleGraph 已移至 graphPipeline.ts，selectors.ts 保留：
//   - currentEntitySet(state): 当前视图应显示的实体 ID 集合
//   - viewHighlightSets(state): 高亮实体/边的 ID 集合
//   - buildPathContext(state): 路径上下文
//   - transitionRenderMode(mode, event): 渲染模式状态机

// ============================================================
// §E  App.tsx: 管道接入点
// ============================================================
// 文件路径: frontend/src/App.tsx
//
// import { analysisToGraph } from './graphPipeline';
//
// const onAnalyze = async () => {
//   const result = await analyzeSql(sql, dialect);
//   const { graph, searchItems, colToTables, invalidEdges } = analysisToGraph(result);
//   setState((s) => ({
//     ...s,
//     backendGraph: graph,
//     backendSearchItems: searchItems,
//     colToTables,
//     backendInvalidEdges: invalidEdges,   // ★ 新增：debug 用
//     ...
//   }));
// };

// ============================================================
// §F  数据流总览
// ============================================================
//
// BackendAnalysisResult (HTTP)
//   │
//   ▼
// normalizeBackendGraph          ← ID 归一化，分离 invalidEdges
//   │
//   ▼
// ensureTerminalOutputEdges     ← 补齐 output 节点和 terminal→output 边
//   │
//   ▼
// layoutLayeredDag              ← 分层 DAG + barycenter + output medianY
//   │
//   ├── buildColToTablesByEdges
//   ├── buildSearchItems
//   │
//   ▼
// visibleGraph                  ← 视图过滤 + table 合成边
//   │
//   ▼
// LineageCanvas                 ← SVG/DIV 渲染
//   ├── buildPortIndexes        ← 端口分配
//   └── routeEdgePath           ← midX lane / loop 路径

// ============================================================
// §G  已知局限与待优化
// ============================================================
//
// 1. 布局仅在 analysisToGraph 和 visibleGraph 时计算，手动拖拽后不重排
// 2. barycenter 4 轮扫描对于 100+ 节点可能需更多轮次
// 3. routeEdgePath 的 midX lane 在节点高度差异大时仍可能有视觉不平滑
// 4. invalidEdges 仅在 state 中记录，未暴露到 UI（可在 Debug 面板展示）
// 5. table 视图合成边 mapping='table_view_synthetic' 仅供前端用，后端无此概念
