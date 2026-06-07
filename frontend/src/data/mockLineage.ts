import type { GraphEdge, GraphNode } from '../types/lineage';

// Shared fixture graph for component and selector tests.
export const subqueryNodes: GraphNode[] = [
  { id: 'n-table-o', entityId: 'table:dwd_order_di', type: 'table', label: 'dwd_order_di', x: 54, y: 142 },
  { id: 'n-table-u', entityId: 'table:dim_user_df', type: 'table', label: 'dim_user_df', x: 54, y: 264 },
  { id: 'n-cte-order', entityId: 'cte:order_base', type: 'cte', label: 'order_base', tag: 'CTE', x: 278, y: 170 },
  { id: 'n-subq-valid', entityId: 'subq:valid_order_subq', type: 'subquery', label: 'valid_order_subq', tag: 'SUBQ', x: 500, y: 170 },
  { id: 'n-cte-metric', entityId: 'cte:metric_base', type: 'cte', label: 'metric_base', tag: 'CTE', x: 742, y: 170 },
  { id: 'n-out-group', entityId: 'out:group', type: 'output', label: 'Output Group', tag: 'OUT', x: 972, y: 170 },
];

export const subqueryEdges: GraphEdge[] = [
  { id: 'e-o-order', source: 'table:dwd_order_di', target: 'cte:order_base', type: 'table' },
  { id: 'e-u-order', source: 'table:dim_user_df', target: 'cte:order_base', type: 'join', mapping: 'map_country' },
  { id: 'e-order-subq', source: 'cte:order_base', target: 'subq:valid_order_subq', type: 'subq' },
  { id: 'e-subq-metric', source: 'subq:valid_order_subq', target: 'cte:metric_base', type: 'cte' },
  { id: 'e-metric-out', source: 'cte:metric_base', target: 'out:group', type: 'output' },
];

export const snapshots = [
  ['snapshot-01-ready-analyze-cta', 'ready state analyze button'],
  ['snapshot-02-analyzed-subquery-dependency', 'default subquery dependency view'],
  ['snapshot-03-selected-current-field-path', 'selected field path'],
  ['snapshot-04-detailpanel-compact-edge-mapping', 'compact edge mapping detail'],
  ['snapshot-05-dirty-reanalyze-stale', 'dirty and stale trust hint'],
  ['snapshot-06-failed-error-summary', 'failed analysis summary'],
  ['snapshot-07-large-graph-subquery-summary', 'large graph summary'],
  ['snapshot-08-node-taxonomy-100-nodes', 'node taxonomy at scale'],
  ['snapshot-09-toolbar-deduplication', 'deduplicated toolbar'],
  ['snapshot-10-1366-canvas-space-budget', '1366x768 canvas budget'],
] as const;

export const milestones = [
  ['M1', 'Base Workbench + PageMode', 'WorkbenchShell / PageModeStore / Splitter'],
  ['M2', 'Analyze + Dirty/Stale Loop', 'AnalyzeClient / TrustStatus / Diagnostics Compact'],
  ['M3', 'Graph Foundation + Adapter', 'ReactFlowAdapter Shell / GraphAdapter / Graph Fact/View/Interaction'],
  ['M4', 'Subquery Dependency + Node Visual', 'SubqueryDependencyViewModel / Node Taxonomy / State Priority'],
  ['M5', 'Search + Field Path', 'SearchBar / Output Capsule / FieldPathApi / PathContextStore'],
  ['M6', 'Detail + Locate + Diagnostics', 'DetailPanel compact / MonacoAdapter / DiagnosticAttentionRule'],
  ['M7', 'UI Hardening + Regression', 'Toolbar Dedup / Primary CTA / Canvas Budget / Snapshots'],
] as const;
