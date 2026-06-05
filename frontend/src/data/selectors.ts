import type { Entity } from '../types/lineage';
import { visibleGraph } from '../graphPipeline';
import type { GraphEdge, GraphNode, GraphRenderMode, PathContext, WorkbenchState } from '../types/lineage';

export function entityName(id?: string | null) {
  if (!id) return '-';

  if (id === 'out:group') return 'Output Group';
  if (id === 'query_result:final' || id === 'out:query_result') return 'Query Result';

  const [prefix, rawName = id] = id.split(/:(.+)/);
  if (prefix === 'physical_table') return rawName.split('.').pop() ?? rawName;

  return rawName;
}

export function entityOf(id?: string | null) {
  if (!id) return undefined;

  const prefix = id.split(':', 1)[0];
  const type: Entity['type'] =
    prefix === 'table' || prefix === 'physical_table'
      ? 'table'
      : prefix === 'cte'
        ? 'cte'
        : prefix === 'subq' || prefix === 'subquery'
          ? 'subquery'
          : prefix === 'out' && id === 'out:group'
            ? 'output_group'
            : prefix === 'out' || prefix === 'output_column'
              ? 'output_field'
              : prefix === 'column' || prefix === 'field' || prefix === 'physical_column'
                ? 'column'
                : prefix === 'expr' || prefix === 'expression'
                  ? 'expression'
                  : prefix === 'join'
                    ? 'join'
                    : 'unknown';

  return {
    id,
    type,
    name: entityName(id),
    comment: 'No backend entity metadata available.',
  } satisfies Entity;
}

export function diagnosticsOf(entityId?: string | null) {
  return [];
}

export function diagnosticsForEntity(state: WorkbenchState, entityId?: string | null) {
  if (!entityId) return [];
  return state.backendDiagnostics?.filter((diagnostic) => diagnostic.entityId === entityId) ?? [];
}

function countReachablePathNodes(state: WorkbenchState, targetId: string) {
  const graph = state.backendGraph;
  if (!graph) return 0;

  const nodeIds = new Set(graph.nodes.map((node) => node.entityId));
  if (!nodeIds.has(targetId)) return 0;

  const reverse = new Map<string, string[]>();
  for (const edge of graph.edges) {
    if (!reverse.has(edge.target)) reverse.set(edge.target, []);
    reverse.get(edge.target)!.push(edge.source);
  }

  const visited = new Set<string>([targetId]);
  const queue = [targetId];

  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const source of reverse.get(current) ?? []) {
      if (visited.has(source)) continue;
      visited.add(source);
      queue.push(source);
    }
  }

  return visited.size;
}

export function buildPathContext(state: WorkbenchState): PathContext {
  const warningCount = state.backendDiagnostics?.length ?? 0;

  if (!state.selectedOutput) {
    return { status: 'idle', display: 'Choose output', nodes: 0, mappings: 0, warnings: warningCount, confidence: 'unknown' };
  }

  let status: PathContext['status'] = 'ready';
  if (state.trustStatus === 'stale') status = 'stale';
  if (state.analysisStatus === 'partial') status = 'partial';
  const outputDiagnostics = diagnosticsForEntity(state, state.selectedOutput);
  if (status === 'ready' && outputDiagnostics.some((diagnostic) => diagnostic.severity === 'warning')) {
    status = 'low_confidence';
  }

  return {
    status,
    display: entityName(state.selectedOutput),
    nodes: countReachablePathNodes(state, state.selectedOutput),
    mappings: 0,
    warnings: warningCount,
    confidence: status === 'low_confidence' ? 'medium' : state.analysisStatus === 'success' ? 'high' : 'unknown',
  };
}

export function deriveAttention(state: WorkbenchState): [string, string, string] {
  if (state.pageMode === 'empty') return ['empty_guide', 'empty', 'page_mode'];
  if (state.pageMode === 'ready' || state.pageMode === 'analyzing') return ['analyze', state.pageMode, 'page_mode'];
  if (state.pageMode === 'failed') return ['error_summary', 'failed', 'diagnostic'];
  if (state.pageMode === 'dirty' || state.trustStatus === 'stale') return ['re_analyze', 'dirty', 'editor_dirty'];
  if (state.selectedMapping) return ['detail_mapping', 'object_selected', 'selection'];
  if (state.selectedEntity && state.detailMode !== 'collapsed' && state.selectedEntity !== 'out:group') return ['detail_mapping', 'object_selected', 'selection'];
  if (state.selectedOutput) return ['current_path', 'path_selected', 'path_context'];
  return ['search_default_output', 'analyzed_no_field', 'path_context'];
}

/** Build mock field-level graph nodes for selector unit tests and local demos. */
export function fieldNodes(state: WorkbenchState): GraphNode[] {
  const output = state.selectedOutput || 'out:order_cnt';
  const nodes: GraphNode[] = [
    { id: 'f-src-order', entityId: 'table:dwd_order_di', type: 'table', label: 'dwd_order_di', x: 70, y: 132 },
    { id: 'f-order-no', entityId: 'field:o.order_no', type: 'table', label: 'order_no', x: 70, y: 210 },
    { id: 'f-order-base', entityId: 'cte:order_base', type: 'cte', label: 'order_base', tag: 'CTE', x: 278, y: 168 },
    { id: 'f-subq', entityId: 'subq:valid_order_subq', type: 'subquery', label: 'valid_order_subq', tag: 'SUBQ', x: 500, y: 168 },
    { id: 'f-expr', entityId: 'expr:valid_order_no', type: 'expression', label: 'CASE', tag: 'EXPR', x: 500, y: 246 },
    { id: 'f-metric', entityId: 'cte:metric_base', type: 'cte', label: 'metric_base', tag: 'CTE', x: 742, y: 168 },
    { id: 'f-output', entityId: output, type: 'output_field', label: entityName(output), tag: 'OUT', x: 972, y: 168 },
  ];

  if (output === 'out:gmv') nodes[1] = { id: 'f-amount', entityId: 'field:o.order_amount', type: 'table', label: 'order_amount', x: 70, y: 210 };
  if (output === 'out:user_cnt') nodes[1] = { id: 'f-user', entityId: 'field:o.user_id', type: 'table', label: 'user_id', x: 70, y: 210 };
  if (output === 'out:country_name') nodes[1] = { id: 'f-country', entityId: 'field:u.country_name', type: 'table', label: 'country_name', x: 70, y: 210 };
  if (output === 'out:avg_order_amount') nodes.push({ id: 'f-avg-expr', entityId: 'expr:avg_order_amount', type: 'expression', label: 'AVG expr', tag: 'EXPR', x: 742, y: 248 });
  if (state.analysisStatus === 'partial') nodes.push({ id: 'f-unknown', entityId: 'unknown:metadata_missing', type: 'unknown', label: 'unknown_col', tag: '?', x: 278, y: 282 });
  return nodes;
}

export function fieldEdges(state: WorkbenchState): GraphEdge[] {
  const out = state.selectedOutput || 'out:order_cnt';
  const edges: GraphEdge[] = [
    { id: 'fe-src-cte', source: 'table:dwd_order_di', target: 'cte:order_base', type: 'table' },
    { id: 'fe-field-cte', source: 'field:o.order_no', target: 'cte:order_base', type: 'table', mapping: 'map_order_cnt' },
    { id: 'fe-cte-subq', source: 'cte:order_base', target: 'subq:valid_order_subq', type: 'subq' },
    { id: 'fe-subq-expr', source: 'subq:valid_order_subq', target: 'expr:valid_order_no', type: 'expr' },
    { id: 'fe-expr-metric', source: 'expr:valid_order_no', target: 'cte:metric_base', type: 'expr', mapping: 'map_order_cnt' },
    { id: 'fe-metric-out', source: 'cte:metric_base', target: out, type: 'output' },
  ];
  if (out === 'out:avg_order_amount') {
    edges.push({ id: 'fe-metric-avg', source: 'cte:metric_base', target: 'expr:avg_order_amount', type: 'expr', mapping: 'map_avg_gmv' });
    edges.push({ id: 'fe-avg-out', source: 'expr:avg_order_amount', target: out, type: 'expr', mapping: 'map_avg_order' });
  }
  return edges;
}

/** View-mode highlight sets for visual treatment in LineageCanvas */
export function viewHighlightSets(state: WorkbenchState): { highlightedEntityIds: Set<string>; highlightedEdgeIds: Set<string> } {
  const gvm = state.graphViewMode ?? 'table';

  const highlightedEntityIds = new Set<string>();
  const highlightedEdgeIds = new Set<string>();

  if (gvm === 'expression') {
    // Highlight expression nodes and expression edges
    const graph = visibleGraph(state);
    for (const node of graph.nodes) {
      if (node.type === 'expression') highlightedEntityIds.add(node.entityId);
    }
    for (const edge of graph.edges) {
      if (edge.type === 'expr') highlightedEdgeIds.add(edge.id);
    }
  }

  if (gvm === 'diagnostics') {
    for (const diagnostic of state.backendDiagnostics ?? []) {
      highlightedEntityIds.add(diagnostic.entityId);
    }
  }

  if (gvm === 'subquery' || gvm === 'semantics') {
    // Highlight nodes with semantic significance (JOIN edges, CTE with aggregation)
    const graph = visibleGraph(state);
    for (const edge of graph.edges) {
      if (edge.type === 'join') highlightedEdgeIds.add(edge.id);
    }
    for (const node of graph.nodes) {
      if (node.type === 'cte') highlightedEntityIds.add(node.entityId);
    }
  }

  return { highlightedEntityIds, highlightedEdgeIds };
}
export function currentEntitySet(state: WorkbenchState) {
  const gvm = state.graphViewMode ?? 'table';
  if (gvm === 'table') {
    const base = state.backendGraph ?? { nodes: [], edges: [] };
    return new Set(base.nodes.filter(n => n.type === 'table' || n.type === 'output').map(n => n.entityId));
  }
  if (gvm === 'subquery' || gvm === 'semantics') {
    const base = state.backendGraph ?? { nodes: [], edges: [] };
    return new Set(base.nodes.map(n => n.entityId));
  }
  if (gvm === 'column') {
    if (state.backendGraph && state.backendGraph.nodes.length) {
      const allowedTypes = new Set<GraphNode['type']>(['column', 'output_field', 'expression', 'unknown']);
      return new Set(state.backendGraph.nodes.filter(n => allowedTypes.has(n.type)).map(n => n.entityId));
    }
    return new Set<string>();
  }
  if (gvm === 'expression' || gvm === 'diagnostics') {
    // Use real backend graph node entity IDs when available
    if (state.backendGraph && state.backendGraph.nodes.length) {
      return new Set(state.backendGraph.nodes.map(n => n.entityId));
    }
    return new Set<string>();
  }
  if (state.backendGraph && (state.renderMode === 'subquery_dependency' || state.renderMode === 'large_graph' || state.renderMode === 'full_graph_preview')) {
    return new Set(state.backendGraph.nodes.map((n) => n.entityId));
  }
  return new Set<string>();
}

export function transitionRenderMode(mode: GraphRenderMode, event: string): { mode: GraphRenderMode; description: string } {
  const rules: Record<string, [GraphRenderMode, boolean, boolean]> = {
    ANALYZE_SUCCESS: ['subquery_dependency', false, true],
    SELECT_OUTPUT_FIELD: ['current_field_path', false, false],
    FOCUS_FIELD: ['focus_field', true, false],
    OPEN_SEMANTIC_MODE: ['semantic_mode', true, false],
    ENTER_LARGE_GRAPH: ['large_graph', true, false],
    OPEN_FULL_PREVIEW: ['full_graph_preview', false, true],
    CLEAR_SELECTION: ['subquery_dependency', false, false],
    ANALYZE_FAILED: ['subquery_dependency', false, false],
  };
  const rule = rules[event];
  if (!rule) return { mode, description: `${mode} · unchanged` };
  const [to, preserveViewport, recomputeLayout] = rule;
  return { mode: to, description: `${mode} -> ${to} · viewport:${preserveViewport ? 'preserve' : 'reset'} · layout:${recomputeLayout ? 'recompute' : 'no'}` };
}
