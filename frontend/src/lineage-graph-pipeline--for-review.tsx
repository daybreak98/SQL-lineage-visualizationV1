// ============================================================
// Lineage Graph Pipeline — 完整血缘图绘制链路
// 文件路径映射（原位置 → 本文）:
//   types/lineage.ts                   → §1 类型定义
//   App.tsx:analysisToGraph            → §2 API→Graph转换 + BFS布局
//   App.tsx:normalize* / tagFor*       → §3 辅助函数
//   data/selectors.ts                  → §4 视图过滤/高亮
//   components/LineageCanvas.tsx       → §5 画布渲染(边+节点+交互)
// ============================================================

// ============================================================
// §1 类型定义 (types/lineage.ts)
// ============================================================

type PageMode = 'empty' | 'ready' | 'analyzing' | 'analyzed' | 'dirty' | 'failed';
type GraphRenderMode = 'subquery_dependency' | 'current_field_path' | 'focus_field' | 'semantic_mode' | 'large_graph' | 'full_graph_preview';
type GraphViewMode = 'table' | 'subquery' | 'column' | 'expression' | 'semantics' | 'diagnostics';
type DetailMode = 'collapsed' | 'compact' | 'expanded';

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

interface SearchItem {
  itemId: string;
  entityId: string;
  displayName: string;
  type: 'output' | 'source' | 'subquery' | 'expression' | 'diagnostic';
  sub: string;
  reason: string;
  confidence: 'high' | 'medium' | 'low';
  warning?: boolean;
}

interface BackendDiagnostic {
  diagnostic_id?: string;
  code: string;
  level: 'info' | 'warning' | 'error';
  message: string;
  suggestion?: string | null;
  related_entity_ids?: string[];
  details?: Record<string, unknown>;
}

interface BackendAnalysisResult {
  schema_version?: string;
  analysis_id: string;
  status: 'success' | 'partial' | 'failed';
  confidence_level?: 'high' | 'medium' | 'low' | 'unknown';
  tables_extracted?: string[];
  columns_extracted?: string[];
  unsupported_features?: string[];
  graph_view_model?: {
    view_mode?: string;
    nodes?: Array<{
      id?: string;
      entity_id?: string | null;
      node_type?: string;
      type?: string;
      label?: string;
      name?: string;
      position?: { x?: number; y?: number };
      x?: number;
      y?: number;
    }>;
    edges?: Array<{
      id?: string;
      source?: string;
      target?: string;
      edge_type?: string;
      type?: string;
      mapping?: string;
    }>;
  };
  diagnostics_report?: {
    diagnostics?: BackendDiagnostic[];
    error_count?: number;
    warning_count?: number;
    info_count?: number;
  };
  summary?: Record<string, number>;
}

interface Diagnostic {
  id: string;
  code: string;
  entityId: string;
  severity: 'info' | 'warning' | 'error';
  reason: string;
  impact: string;
  action: string;
}

interface WorkbenchState {
  pageMode: PageMode;
  renderMode: GraphRenderMode;
  graphViewMode: GraphViewMode;
  detailMode: DetailMode;
  selectedOutput: string | null;
  selectedEntity: string;
  selectedMapping: string | null;
  trustStatus: 'trusted' | 'stale' | 'untrusted';
  lastTransition?: string;
  positions: Record<string, { x: number; y: number }>;
  backendGraph?: { nodes: GraphNode[]; edges: GraphEdge[] };
  backendSearchItems?: SearchItem[];
  backendDiagnostics?: Diagnostic[];
  backendMessage?: string;
  colToTables?: Record<string, string[]>;
  // ... 其他字段省略
}

// ============================================================
// §2 API响应 → 前端Graph转换 + BFS层级布局 (App.tsx)
// ============================================================

function normalizeEdgeType(type?: string): GraphEdge['type'] {
  if (type === 'column_lineage') return 'projection';
  if (type === 'table_to_result') return 'table';
  if (type === 'table_to_cte') return 'table';
  if (type === 'cte_dependency') return 'cte';
  if (type === 'cte_to_result') return 'output';
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
  return 'output';
}

function tagForNodeType(type?: string) {
  if (type === 'output_column' || type === 'output_field') return 'OUT';
  if (type === 'column') return 'COL';
  if (type === 'table') return 'TBL';
  if (type === 'expression') return 'EXPR';
  if (type === 'unknown') return '?';
  return undefined;
}

/**
 * ★ 核心函数：将后端 AnalysisResult 转换为前端 GraphNode[]/GraphEdge[]，
 *   同时计算 BFS 层级布局（每个节点的 x, y 坐标）。
 *
 * ★ 问题区域：
 *   1. BFS算法嵌套在数据转换中，耦合度高
 *   2. 列级血缘(column_lineage)和结构级(subquery_dependency)两套布局混在一起
 *   3. 布局参数 (baseX=72, levelGap=170, yGap=56) 硬编码
 *   4. output节点Y坐标取父节点均值，单一输出节点时位置可能偏移
 *   5. colToTables 的匹配逻辑用字符串 contains/findIndex 不可靠
 *   6. 两条CTE引用同一物理表(lvXJ)已用edge分组偏移处理（见§5）
 */
function analysisToGraph(result: BackendAnalysisResult): {
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  searchItems: SearchItem[];
  colToTables: Record<string, string[]>;
} {
  const apiNodes = result.graph_view_model?.nodes || [];
  const apiEdges = result.graph_view_model?.edges || [];

  // ─── 分支1: 纯列级血缘图 ───
  const hasColumnLineageGraph = apiNodes.some((node) => {
    const ntype = node.node_type || node.type || '';
    return ntype === 'physical_column' || ntype === 'output_column';
  });

  if (hasColumnLineageGraph && !apiNodes.some((node) =>
    ['table', 'cte', 'subquery', 'output'].includes(node.node_type || node.type || '')
  )) {
    const sourceNodes = apiNodes.filter((node) => (node.node_type || node.type) === 'physical_column');
    const outputNodes = apiNodes.filter((node) => (node.node_type || node.type) === 'output_column');
    const sourceIndex = new Map(sourceNodes.map((node, index) => [node.id || `source-${index}`, index]));
    const outputIndex = new Map(outputNodes.map((node, index) => [node.id || `output-${index}`, index]));

    /** ★ 列级节点布局：按源/输出分行排列，左右固定列 */
    const nodes: GraphNode[] = apiNodes.map((node, index) => {
      const ntype = node.node_type || node.type || '';
      const id = node.id || `api-node-${index}`;
      const isOutput = ntype === 'output_column';
      const row = isOutput ? outputIndex.get(id) ?? index : sourceIndex.get(id) ?? index;
      return {
        id,
        entityId: node.entity_id || id,
        type: normalizeNodeType(ntype),
        label: node.label || node.name || id,
        tag: tagForNodeType(ntype),
        x: node.position?.x ?? node.x ?? (isOutput ? 380 : 70),
        y: node.position?.y ?? node.y ?? 70 + row * 76,
      };
    });

    const nodeIds = new Set(nodes.map((node) => node.entityId));
    const edges: GraphEdge[] = apiEdges
      .filter((edge) => edge.source && edge.target && nodeIds.has(edge.source) && nodeIds.has(edge.target))
      .map((edge, index) => ({
        id: edge.id || `api-edge-${index}`,
        source: edge.source!,
        target: edge.target!,
        type: normalizeEdgeType(edge.edge_type || edge.type),
        mapping: edge.mapping || edge.id,
      }));

    const colToTables: Record<string, string[]> = {};
    edges.forEach((edge) => {
      colToTables[edge.target] = colToTables[edge.target] || [];
      if (!colToTables[edge.target].includes(edge.source)) {
        colToTables[edge.target].push(edge.source);
      }
    });

    const searchItems: SearchItem[] = [
      ...outputNodes.map((node, index) => ({
        itemId: `search-output-${index}`,
        entityId: node.entity_id || node.id || `output-${index}`,
        displayName: node.label || node.name || node.id || `output-${index}`,
        type: 'output' as const,
        sub: `from: ${(colToTables[node.id || ''] || []).join(', ') || 'unknown source'}`,
        reason: 'column lineage',
        confidence: (colToTables[node.id || '']?.length ? 'high' : 'low') as 'high' | 'low',
        warning: !colToTables[node.id || '']?.length,
      })),
      ...sourceNodes.map((node, index) => ({
        itemId: `search-source-${index}`,
        entityId: node.entity_id || node.id || `source-${index}`,
        displayName: node.label || node.name || node.id || `source-${index}`,
        type: 'source' as const,
        sub: 'physical column',
        reason: 'backend',
        confidence: 'high' as const,
      })),
    ];

    return { graph: { nodes, edges }, searchItems, colToTables };
  }

  // ─── 分支2: 结构级图（CTE/子查询/表）───
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  let outputColEntities: { label: string; entityId: string }[] = [];
  let tableCol = 0;
  const startY = 72;
  const rowH = 64;
  let fieldRow = 0;

  let colToTables: Record<string, string[]> = {};
  let maxLevel = 0;
  const baseX = 72;
  const levelGap = 170;
  const yGap = 62;        // ★ 与上面的 yGap=56 不一致（后者在BFS布局中被重新声明覆盖）
  const structureNodeTypes = new Set(['table', 'cte', 'subquery', 'output']);

  if (apiNodes.length) {
    /** ★ 第一遍：按类型创建节点，初始暂存列位置 */
    apiNodes.forEach((node, i) => {
      const ntype = node.node_type || node.type || '';
      const label = node.label || node.name || '';
      const eid = node.entity_id || node.id || '';
      if (ntype === 'table' || ntype === 'cte' || ntype === 'subquery') {
        nodes.push({
          id: node.id || `api-node-${i}`,
          entityId: eid,
          type: ntype as GraphNode['type'],
          label: label.split('.').pop() || label,
          tag: ntype === 'cte' ? 'CTE' : ntype === 'subquery' ? 'SUBQ' : undefined,
          x: 60, y: startY + tableCol * rowH,
        });
        tableCol++;
      } else if (ntype === 'output_column') {
        outputColEntities.push({ label, entityId: eid });
        nodes.push({
          id: node.id || `api-node-${i}`,
          entityId: eid,
          type: 'output_field',
          label,
          tag: 'OUT',
          x: 420,
          y: 280 + Math.max(0, fieldRow - 1) * 76,
        });
      } else if (ntype === 'output') {
        nodes.push({ id: node.id || `api-node-${i}`, entityId: eid, type: 'output', label: label || 'Query Result', tag: 'OUT', x: 60, y: startY + tableCol * rowH });
        tableCol++;
      } else if (ntype === 'physical_column') {
        nodes.push({ id: node.id || `api-node-${i}`, entityId: eid, type: 'column', label, tag: 'COL', x: 70, y: 280 + fieldRow * 76 });
        fieldRow++;
      }
    });

    /** ★ BFS层级计算：从物理表(level=0)开始，沿边传播层级 */
    const deps: Record<string, string[]> = {};
    apiEdges.forEach((edge) => {
      const src = edge.source || '';
      const tgt = edge.target || '';
      if (src && tgt) {
        deps[tgt] = deps[tgt] || [];
        deps[tgt].push(src);
      }
    });

    const levels: Record<string, number> = {};
    nodes.forEach(n => { if (n.type === 'table') levels[n.entityId] = 0; });

    let changed = true;
    while (changed) {
      changed = false;
      nodes.forEach(n => {
        if (n.type !== 'cte' && n.type !== 'subquery') return;
        if (levels[n.entityId] !== undefined) return;
        const srcs = deps[n.entityId] || [];
        if (srcs.length === 0) {
          levels[n.entityId] = 1;
          changed = true;
        } else {
          const maxSrc = Math.max(...srcs.map(s => levels[s] ?? -1));
          if (maxSrc >= 0) { levels[n.entityId] = maxSrc + 1; changed = true; }
        }
      });
    }

    /** ★ 结构节点布局：X = baseX + level * levelGap，Y = 层级内按行排 */
    const yGap_Local = 56;  // ★ 注意：此处 yGap 与外层 yGap=62 不同，外层声明被覆盖
    const levelRows: Record<number, number> = {};
    const structureNodes = nodes.filter(n => structureNodeTypes.has(n.type));
    maxLevel = Math.max(0, ...Object.values(levels));

    structureNodes.filter(n => n.type === 'output').forEach(n => {
      levels[n.entityId] = maxLevel + 1;
    });

    structureNodes.filter(n => n.type !== 'output').forEach(n => {
      const lvl = levels[n.entityId] ?? 0;
      n.x = baseX + lvl * levelGap;
      const row = levelRows[lvl] || 0;
      n.y = startY + row * yGap_Local;
      levelRows[lvl] = row + 1;
    });

    /** ★ output节点Y坐标取前驱节点Y均值 */
    structureNodes.filter(n => n.type === 'output').forEach(outputNode => {
      const incomingSources = apiEdges
        .filter(edge => (edge.target || '') === outputNode.entityId)
        .map(edge => structureNodes.find(n => n.entityId === (edge.source || '')))
        .filter((n): n is GraphNode => Boolean(n));
      const referenceNodes = incomingSources.length > 0 ? incomingSources : structureNodes.filter(n => n.type !== 'output');
      const avgY = referenceNodes.length > 0
        ? referenceNodes.reduce((sum, n) => sum + n.y, 0) / referenceNodes.length
        : startY;
      outputNode.x = baseX + (maxLevel + 1) * levelGap;
      outputNode.y = avgY;
    });

    // ★ colToTables：用字符串包含匹配将边对应到物理表
    colToTables = {};
    const physicalTableIds = new Set<string>();
    apiNodes.forEach((node) => {
      if (node.node_type === 'table' || node.type === 'table') {
        physicalTableIds.add(node.entity_id || node.id || '');
      }
    });

    apiEdges.forEach((edge, ei) => {
      const src = edge.source || '';
      const tgt = edge.target || '';
      if (!src || !tgt) return;
      colToTables[tgt] = colToTables[tgt] || [];
      let matched = false;
      for (const tid of physicalTableIds) {
        if (src.includes(tid.split(':').pop() || '')) {
          if (!colToTables[tgt].includes(tid)) colToTables[tgt].push(tid);
          matched = true;
        }
      }
      if (!matched && src.includes(':cte.')) {
        physicalTableIds.forEach(tid => {
          if (!colToTables[tgt].includes(tid)) colToTables[tgt].push(tid);
        });
      }
      edges.push({
        id: edge.id || `api-edge-${ei}`,
        source: src,
        target: tgt,
        type: normalizeEdgeType(edge.edge_type || edge.type),
        mapping: edge.mapping || edge.id,
      });
    });
  } else {
    // 无 graph_view_model 时的退化处理
    const tables = result.tables_extracted || [];
    tables.forEach((table, index) => {
      nodes.push({ id: `api-table-${index}`, entityId: `table:${table}`, type: 'table', label: table.split('.').pop() || table, x: 60, y: startY + index * rowH });
    });
    tables.forEach((table, index) => {
      edges.push({ id: `api-table-edge-${index}`, source: `table:${table}`, target: 'out:query_result', type: 'table' });
    });
  }

  // ★ 确保 output 节点存在
  const existingResult = nodes.find(n => n.type === 'output');
  const resultId = existingResult?.entityId || 'out:query_result';
  const tableNodes = nodes.filter(n => n.type === 'table' || n.type === 'cte' || n.type === 'subquery');
  const shortCols = outputColEntities.map(c => c.label.includes('.') ? c.label.split('.').pop()! : c.label);
  const resultLabel = shortCols.length > 0 ? `Query Result (${shortCols.length} cols)` : 'Query Result';
  const avgY = tableNodes.length > 0 ? tableNodes.reduce((sum, n) => sum + n.y, 0) / tableNodes.length : startY;
  const resultX = baseX + (maxLevel + 1) * levelGap;

  if (!existingResult) {
    nodes.push({ id: 'api-query-result', entityId: 'out:query_result', type: 'output', label: resultLabel, tag: 'OUT', x: resultX, y: avgY });
  }

  const searchItems: SearchItem[] = [
    { itemId: 'search-query-result', entityId: resultId, displayName: resultLabel, type: 'output', sub: `${tableNodes.length} tables · ${outputColEntities.length} cols`, reason: 'sql analyze', confidence: result.status === 'partial' ? 'medium' : 'high' },
    ...outputColEntities.map((col, i) => {
      const tables = colToTables[col.entityId];
      const hasSource = tables && tables.length > 0;
      return {
        itemId: `search-out-${i}`,
        entityId: col.entityId,
        displayName: col.label,
        type: 'output' as const,
        sub: hasSource ? `from: ${tables.join(', ')}` : 'unknown source',
        reason: hasSource ? `→ ${tables.join(', ')}` : '无法确认字段来源',
        confidence: hasSource ? ('high' as const) : ('low' as const),
        warning: !hasSource,
      };
    }),
    ...tableNodes.map(tn => ({ itemId: `search-${tn.entityId}`, entityId: tn.entityId, displayName: tn.label, type: 'source' as const, sub: tn.type, reason: 'backend', confidence: 'high' as const })),
  ];

  return { graph: { nodes, edges }, searchItems, colToTables };
}

// ============================================================
// §3 视图过滤 (data/selectors.ts)
// ============================================================

/**
 * ★ 根据 graphViewMode 过滤节点和边。
 * ★ 问题：table 模式下会重新布局节点（x=72/292），与 analysisToGraph 的布局冲突。
 */
function visibleGraph(state: WorkbenchState): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const gvm = state.graphViewMode ?? 'table';

  if (gvm === 'subquery') {
    if (!state.backendGraph) return { nodes: [], edges: [] };
    const base = state.backendGraph;
    const allowedTypes = new Set<GraphNode['type']>(['table', 'cte', 'subquery', 'output']);
    const filteredNodes = base.nodes.filter(n => allowedTypes.has(n.type));
    const filteredIds = new Set(filteredNodes.map(n => n.entityId));
    return {
      nodes: filteredNodes,
      edges: base.edges.filter(e => filteredIds.has(e.source) && filteredIds.has(e.target)),
    };
  }

  if (gvm === 'table') {
    if (!state.backendGraph) return { nodes: [], edges: [] };
    const base = state.backendGraph;
    const filteredNodes = base.nodes.filter(n => n.type === 'table' || n.type === 'output');
    const filteredIds = new Set(filteredNodes.map(n => n.entityId));
    const tableEdges = base.edges.filter(e => filteredIds.has(e.source) && filteredIds.has(e.target));

    // ★ 表视图下为所有table节点到output合成直连边
    const outputNodes = filteredNodes.filter(n => n.type === 'output');
    const tableNodes = filteredNodes.filter(n => n.type === 'table');
    const synthesizedEdges: GraphEdge[] = [];
    if (outputNodes.length === 1) {
      const outputId = outputNodes[0].entityId;
      for (const table of tableNodes) {
        if (!tableEdges.some(e => e.source === table.entityId && e.target === outputId)) {
          synthesizedEdges.push({ id: `table-view:${table.entityId}->${outputId}`, source: table.entityId, target: outputId, type: 'table' });
        }
      }
    }

    // ★★★ 关键问题：table模式下强制重新布局，覆盖 analysisToGraph 的BFS布局
    const tableLayoutNodes = filteredNodes.map((node, index) => {
      if (node.type === 'table') {
        const tableIndex = tableNodes.findIndex(t => t.entityId === node.entityId);
        return { ...node, x: 72, y: 72 + tableIndex * 58 };
      }
      const outputY = tableNodes.length > 0 ? 72 + ((tableNodes.length - 1) * 58) / 2 : 72 + index * 58;
      return { ...node, x: 292, y: outputY };
    });

    return { nodes: tableLayoutNodes, edges: [...tableEdges, ...synthesizedEdges] };
  }

  if (gvm === 'column') {
    if (state.backendGraph && state.backendGraph.nodes.length) {
      const allowedTypes = new Set<GraphNode['type']>(['column', 'output_field', 'expression', 'unknown']);
      const filteredNodes = state.backendGraph.nodes.filter(n => allowedTypes.has(n.type));
      const filteredIds = new Set(filteredNodes.map(n => n.entityId));
      return {
        nodes: filteredNodes,
        edges: state.backendGraph.edges.filter(e => filteredIds.has(e.source) && filteredIds.has(e.target)),
      };
    }
    return { nodes: [], edges: [] };
  }

  if (gvm === 'semantics') {
    return state.backendGraph ?? { nodes: [], edges: [] };
  }

  if (gvm === 'expression' || gvm === 'diagnostics') {
    return state.backendGraph ?? { nodes: [], edges: [] };
  }

  if (state.backendGraph && (state.renderMode === 'subquery_dependency' || state.renderMode === 'large_graph' || state.renderMode === 'full_graph_preview')) {
    return state.backendGraph;
  }

  return { nodes: [], edges: [] };
}

/**
 * ★ 当前视图下应显示的实体ID集合
 */
function currentEntitySet(state: WorkbenchState) {
  const gvm = state.graphViewMode ?? 'table';
  if (gvm === 'table') {
    const base = state.backendGraph ?? { nodes: [], edges: [] };
    return new Set(base.nodes.filter(n => n.type === 'table' || n.type === 'output').map(n => n.entityId));
  }
  if (gvm === 'column') {
    if (state.backendGraph && state.backendGraph.nodes.length) {
      const allowedTypes = new Set<GraphNode['type']>(['column', 'output_field', 'expression', 'unknown']);
      return new Set(state.backendGraph.nodes.filter(n => allowedTypes.has(n.type)).map(n => n.entityId));
    }
    return new Set<string>();
  }
  if (state.backendGraph) {
    return new Set(state.backendGraph.nodes.map((n) => n.entityId));
  }
  return new Set<string>();
}

function viewHighlightSets(state: WorkbenchState): { highlightedEntityIds: Set<string>; highlightedEdgeIds: Set<string> } {
  const gvm = state.graphViewMode ?? 'table';
  const highlightedEntityIds = new Set<string>();
  const highlightedEdgeIds = new Set<string>();

  if (gvm === 'expression') {
    const graph = visibleGraph(state);
    for (const node of graph.nodes) { if (node.type === 'expression') highlightedEntityIds.add(node.entityId); }
    for (const edge of graph.edges) { if (edge.type === 'expr') highlightedEdgeIds.add(edge.id); }
  }
  if (gvm === 'diagnostics') {
    const allDiagnostics = state.backendDiagnostics ?? [];
    for (const d of allDiagnostics) { highlightedEntityIds.add(d.entityId); }
  }
  if (gvm === 'subquery' || gvm === 'semantics') {
    const graph = visibleGraph(state);
    for (const edge of graph.edges) { if (edge.type === 'join') highlightedEdgeIds.add(edge.id); }
    for (const node of graph.nodes) { if (node.type === 'cte') highlightedEntityIds.add(node.entityId); }
  }
  return { highlightedEntityIds, highlightedEdgeIds };
}

// ============================================================
// §4 画布渲染 (components/LineageCanvas.tsx) —— 核心可视化
// ============================================================

// -- 纯函数工具 --
function nodeBox(type: GraphNode['type']) {
  if (type === 'output') return { width: 132, height: 32 };
  if (type === 'subquery') return { width: 138, height: 32 };
  if (type === 'cte' || type === 'output_field' || type === 'expression') return { width: 125, height: 30 };
  if (type === 'column') return { width: 122, height: 29 };
  return { width: 118, height: 29 };
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function fitZoom(bounds: { width: number; height: number } | null, viewport: { width: number; height: number }) {
  if (!bounds || viewport.width === 0 || viewport.height === 0) return 1.25;
  const xFit = (viewport.width - 96) / bounds.width;
  const yFit = (viewport.height - 104) / bounds.height;
  return clamp(Math.min(1.15, xFit, yFit), 0.35, 1.15);
}

function centerOffset(
  bounds: { minX: number; minY: number; width: number; height: number } | null,
  viewport: { width: number; height: number },
  zoom: number,
) {
  if (!bounds || viewport.width === 0 || viewport.height === 0) return { x: 0, y: 0 };
  const padX = 32;
  const padY = 36;
  const scaledWidth = bounds.width * zoom;
  const scaledHeight = bounds.height * zoom;
  return {
    x: scaledWidth <= viewport.width - padX * 2
      ? (viewport.width - scaledWidth) / 2 - bounds.minX * zoom
      : padX - bounds.minX * zoom,
    y: scaledHeight <= viewport.height - padY * 2
      ? (viewport.height - scaledHeight) / 2 - bounds.minY * zoom
      : padY - bounds.minY * zoom,
  };
}

/**
 * ★ 边路由：对相同 source→target 的并行边做Y轴偏移，减少重叠
 *
 * ★ 问题：
 *   1. 仅处理完全相同的 source::target 对，不同层级但路径接近的边不处理
 *   2. 偏移量硬编码为 16px
 *   3. 贝塞尔控制点弯曲仅依赖水平距离，不考虑垂直高度差
 */
function renderEdges(
  graph: { nodes: GraphNode[]; edges: GraphEdge[] },
  positions: Record<string, { x: number; y: number }>,
  byEntity: Record<string, GraphNode>,
  current: Set<string>,
  selectedEdges: Set<string>,
  selectedNodeIds: Set<string>,
  hasActiveSelection: boolean,
  highlights: { highlightedEntityIds: Set<string>; highlightedEdgeIds: Set<string> },
  selectedMapping: string | null,
  setState: (s: WorkbenchState) => void,
) {
  // ★ 分组并行边
  const edgeGroups = new Map<string, GraphEdge[]>();
  for (const edge of graph.edges) {
    const key = `${edge.source}::${edge.target}`;
    if (!edgeGroups.has(key)) edgeGroups.set(key, []);
    edgeGroups.get(key)!.push(edge);
  }
  const edgeIndexMap = new Map<string, number>();
  for (const [, group] of edgeGroups) {
    group.forEach((edge, i) => edgeIndexMap.set(edge.id, i));
  }
  const edgeGroupSizeMap = new Map<string, number>();
  for (const [key, group] of edgeGroups) edgeGroupSizeMap.set(key, group.length);

  return graph.edges.map((edge: GraphEdge) => {
    const s = byEntity[edge.source];
    const t = byEntity[edge.target];
    if (!s || !t) return null;
    const sp = positions[s.id] ?? { x: s.x, y: s.y };
    const tp = positions[t.id] ?? { x: t.x, y: t.y };
    const sourceBox = nodeBox(s.type);
    const targetBox = nodeBox(t.type);
    const sx = sp.x + sourceBox.width;
    const sy = sp.y + sourceBox.height / 2;
    const tx = tp.x;
    const ty = tp.y + targetBox.height / 2;
    const dx = tx - sx;
    const dy = ty - sy;

    // ★ 并行边Y偏移
    const groupSize = edgeGroupSizeMap.get(`${edge.source}::${edge.target}`) ?? 1;
    const edgeIdx = edgeIndexMap.get(edge.id) ?? 0;
    const offsetY = groupSize > 1 ? (edgeIdx - (groupSize - 1) / 2) * 16 : 0;

    const shortEdge = Math.abs(dx) < 96 && Math.abs(dy) < 34;
    const bend = Math.min(72, Math.max(28, Math.abs(dx) * 0.35));

    // ★ 贝塞尔曲线路径
    const edgePath = shortEdge
      ? `M ${sx} ${sy + offsetY} L ${tx} ${ty + offsetY}`
      : `M ${sx} ${sy + offsetY} C ${sx + bend} ${sy + offsetY}, ${tx - bend} ${ty + offsetY}, ${tx} ${ty + offsetY}`;

    const isCurrent = (current.has(edge.source) && current.has(edge.target)) || selectedMapping === edge.mapping;
    const isSelectedEdge = selectedEdges.has(edge.id);
    const isRelated = isSelectedEdge || (selectedNodeIds.has(edge.source) && selectedNodeIds.has(edge.target));
    const dimmed = hasActiveSelection && !isRelated;
    const isViewHighlighted = highlights.highlightedEdgeIds.has(edge.id);
    const markerEnd = (isCurrent || isSelectedEdge) ? 'url(#arrowPrimary)' : 'url(#arrowDefault)';

    // ★ 用JSX描述（实际渲染时使用React.createElement或JSX）
    return {
      key: edge.id,
      source: edge.source,
      target: edge.target,
      mapping: edge.mapping,
      path: edgePath,
      type: edge.type,
      current: isCurrent,
      dimmed,
      viewHighlight: isViewHighlighted,
      selected: isSelectedEdge,
      markerEnd,
    };
  }).filter(Boolean);
}

/**
 * ★ 拖拽/缩放/平移交互系统
 *
 * ★ 问题：
 *   1. 两套鼠标监听：组件 onMouseMove + window mousemove
 *   2. requestAnimationFrame 帧同步与 setState 异步可能产生竞态
 *   3. 拖拽结束后位置写入 state.positions，与 analysisToGraph 布局并存，优先级靠合并顺序控制
 */
type DragState = { id: string; ox: number; oy: number };
type PanDragState = { x: number; y: number; panX: number; panY: number };

function useLineageInteraction(
  viewportRef: { current: HTMLDivElement | null },
  viewOffset: { x: number; y: number },
  zoom: number,
  graphBounds: { width: number; height: number; minX: number; minY: number } | null,
  viewportSize: { width: number; height: number },
  positions: Record<string, { x: number; y: number }>,
  setState: (s: WorkbenchState) => void,
) {
  // — 此处伪代码，实际使用React hooks —
  // const [drag, setDrag] = useState<DragState | null>(null);
  // const [panDrag, setPanDrag] = useState<PanDragState | null>(null);
  // const [draftPositions, setDraftPositions] = useState<Record<string, { x: number; y: number }>>({});
  // const [manualPan, setManualPan] = useState({ x: 0, y: 0 });
  // const [zoomOverride, setZoomOverride] = useState<number | null>(null);
  //
  // ★ 拖拽启动: 节点 mousedown → setDrag
  // ★ 平移启动: 画布空白区域 mousedown → setPanDrag
  // ★ 缩放: onWheel → zoomBy()
  //
  // applyPointer(clientX, clientY):
  //   - panDrag存在 → setManualPan(偏移)
  //   - drag存在 → setDraftPositions(屏幕坐标转画布坐标)
  //
  // queuePointer(clientX, clientY):
  //   - window mousemove → requestAnimationFrame → applyPointer (帧同步)
  //
  // ★ 组件级：onMouseMove → applyPointer (立即更新)
  // ★ 窗口级：window mousemove → queuePointer → rAF → applyPointer (兜底)
  //
  // finishInteraction():
  //   - 将draftPositions合并到state.positions
  //   - 清理drag/panDrag/frameRef
  //   - 恢复body.userSelect
}

// ============================================================
// §5 渲染输出结构（LineageCanvas 实际DOM结构）
// ============================================================

/**
 * ★ DOM 结构：
 *
 * <div.viewport>                        ← 视口容器，ResizeObserver监听
 *   <!-- 缩放/复位按钮 -->
 *   <div style="position:absolute"> [-] [zoom%] [+] [Reset] </div>
 *
 *   <!-- 提示信息 -->
 *   <div.message> 状态提示 </div>
 *
 *   <div.canvas-transform>              ← 平移变换层
 *     transform: translate(viewOffset.x, viewOffset.y)
 *
 *     <div.stage>                       ← 缩放变换层
 *       transform: scale(zoom)
 *
 *       <svg.edge-layer>                ← ★ SVG边图层
 *         <defs>
 *           <marker id="arrowDefault" />  ← 灰色箭头
 *           <marker id="arrowPrimary" />  ← 蓝色箭头
 *         </defs>
 *         { renderEdges(...) }          ← §4 边渲染
 *       </svg>
 *
 *       { graph.nodes.map(node => (      ← ★ DIV节点图层
 *         <div.node
 *           data-type={node.type}
 *           data-selected / data-current / data-dimmed / data-dragging
 *           onMouseDown → startDrag
 *           onClick → selectEntity
 *           onDoubleClick → onNodeDoubleClick
 *           style={{ left: p.x, top: p.y }}
 *         >
 *           <span.strip />              ← 颜色条
 *           <span.title>{label}</span>  ← 标签文本
 *           <span.state-dot />          ← 状态点
 *         </div>
 *       ))}
 *     </div>
 *   </div>
 *
 *   <div.stats>                         ← 调试统计面板
 *     mode / view / visible / layout / labels
 *   </div>
 * </div>
 */

// ============================================================
// §6 已知问题汇总
// ============================================================

/**
 * 【布局层】
 * 1. analysisToGraph 中 BFS 层级计算与节点创建耦合，应抽离为独立 layout solver
 * 2. 两套 yGap 常量（62 和 56）不一致
 * 3. visibleGraph 的 table 模式会覆盖 analysisToGraph 的布局（x 坐标从 72→baseX 变 72→292）
 * 4. output 节点 Y 坐标用前驱均值，多输出时缺少输出节点间的间隔逻辑
 * 5. 列级血缘图使用固定行高 76，不考虑节点标签长度导致的溢出
 *
 * 【边路由层】
 * 6. 仅处理完全相同的 source::target 对，不处理交叉边或密集区域
 * 7. 贝塞尔弯曲仅依赖水平距离 (Math.abs(dx)*0.35)，垂直方向无调整
 * 8. 短边判定阈值硬编码 (96, 34)，大缩放时可能出现异常
 * 9. 箭头标记与边线颜色逻辑分散在 isCurrent/isSelectedEdge 判断中
 *
 * 【交互层】
 * 10. 双路鼠标监听（组件内/窗口级）增加维护复杂度
 * 11. requestAnimationFrame + setState 异步可能导致拖拽结束位置不一致
 * 12. 平移/缩放复位依赖 useEffect([backendGraph, graphViewMode])，切换视图模式时会丢失手动平移
 * 13. positions 状态同时来自 analysisToGraph 初始布局、手动拖拽、draftPositions，
 *     合并优先级在 useMemo 中通过对象展开控制，缺乏显式来源标记
 *
 * 【体/转换层】
 * 14. normalizeEdgeType/normalizeNodeType 作为独立 switch，后端增删类型时需同步维护
 * 15. colToTables 字符串包含匹配 (`src.includes(tid.split(':').pop())`) 不可靠
 * 16. 当 apiNodes 为空但 tables_extracted 有数据时的退化路径与正常路径布局不一致
 */
