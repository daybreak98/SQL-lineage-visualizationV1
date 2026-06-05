import type { Diagnostic, EdgeMapping, Entity, GraphEdge, GraphNode, SearchItem, SourceLocation } from '../types/lineage';

export const entities: Record<string, Entity> = {
  'table:dwd_order_di': { id: 'table:dwd_order_di', type: 'table', name: 'dwd_order_di', comment: '订单明细事实表，默认作为结构图上下文节点。' },
  'table:dim_user_df': { id: 'table:dim_user_df', type: 'table', name: 'dim_user_df', comment: '用户维表，提供国家维度。' },
  'cte:order_base': { id: 'cte:order_base', type: 'cte', name: 'order_base', comment: '订单明细清洗与维表补充。' },
  'subq:valid_order_subq': { id: 'subq:valid_order_subq', type: 'subquery', name: 'valid_order_subq', comment: '默认结构视图中的子查询节点：过滤有效订单。' },
  'cte:metric_base': { id: 'cte:metric_base', type: 'cte', name: 'metric_base', comment: '按 country_name 聚合指标。' },
  'out:group': { id: 'out:group', type: 'output_group', name: 'Output Group', comment: '稳定输出分组节点。默认结构图不渲染 20+ output fields。' },
  'out:country_name': { id: 'out:country_name', type: 'output_field', name: 'country_name', comment: '最终输出维度字段。' },
  'out:order_cnt': { id: 'out:order_cnt', type: 'output_field', name: 'order_cnt', comment: 'count distinct valid_order_no。' },
  'out:user_cnt': { id: 'out:user_cnt', type: 'output_field', name: 'user_cnt', comment: 'count distinct user_id。' },
  'out:gmv': { id: 'out:gmv', type: 'output_field', name: 'gmv', comment: 'sum(order_amount)。' },
  'out:avg_order_amount': { id: 'out:avg_order_amount', type: 'output_field', name: 'avg_order_amount', comment: 'gmv / nullif(order_cnt, 0)，低置信定位。' },
  'field:o.order_no': { id: 'field:o.order_no', type: 'column', name: 'order_no', comment: '订单号，order_cnt 的源字段。' },
  'field:o.user_id': { id: 'field:o.user_id', type: 'column', name: 'user_id', comment: '用户 ID，user_cnt 源字段。' },
  'field:o.order_amount': { id: 'field:o.order_amount', type: 'column', name: 'order_amount', comment: '订单金额，gmv 源字段。' },
  'field:u.country_name': { id: 'field:u.country_name', type: 'column', name: 'country_name', comment: '国家名称。' },
  'expr:valid_order_no': { id: 'expr:valid_order_no', type: 'expression', name: 'CASE valid_order', comment: 'case when o.is_valid=1 then o.order_no end。' },
  'expr:avg_order_amount': { id: 'expr:avg_order_amount', type: 'expression', name: 'AVG amount expr', comment: 'gmv/order_cnt 表达式。' },
  'unknown:metadata_missing': { id: 'unknown:metadata_missing', type: 'unknown', name: 'unknown_col', comment: '模拟 UNKNOWN_COLUMN / metadata_missing 风险节点。' },
};

export const sourceLocations: Record<string, SourceLocation> = {
  'field:o.order_no': { entityId: 'field:o.order_no', line: 4, col: 5, rangeType: 'exact', raw: 'o.order_no' },
  'field:o.user_id': { entityId: 'field:o.user_id', line: 3, col: 5, rangeType: 'exact', raw: 'o.user_id' },
  'field:o.order_amount': { entityId: 'field:o.order_amount', line: 5, col: 5, rangeType: 'exact', raw: 'o.order_amount' },
  'field:u.country_name': { entityId: 'field:u.country_name', line: 8, col: 5, rangeType: 'exact', raw: 'u.country_name' },
  'expr:valid_order_no': { entityId: 'expr:valid_order_no', line: 6, col: 5, rangeType: 'approximate', raw: 'case when o.is_valid = 1 then o.order_no end' },
  'out:order_cnt': { entityId: 'out:order_cnt', line: 30, col: 3, rangeType: 'exact', raw: 'order_cnt' },
  'out:user_cnt': { entityId: 'out:user_cnt', line: 31, col: 3, rangeType: 'exact', raw: 'user_cnt' },
  'out:gmv': { entityId: 'out:gmv', line: 32, col: 3, rangeType: 'exact', raw: 'gmv' },
  'out:avg_order_amount': { entityId: 'out:avg_order_amount', line: 33, col: 3, rangeType: 'approximate', raw: 'gmv / nullif(order_cnt, 0)' },
  'cte:order_base': { entityId: 'cte:order_base', line: 1, col: 1, rangeType: 'approximate', raw: 'with order_base as (...)' },
  'subq:valid_order_subq': { entityId: 'subq:valid_order_subq', line: 15, col: 1, rangeType: 'approximate', raw: 'valid_order_subq as (...)' },
  'cte:metric_base': { entityId: 'cte:metric_base', line: 23, col: 1, rangeType: 'approximate', raw: 'metric_base as (...)' },
};

export const diagnostics: Diagnostic[] = [
  { id: 'diag_join', code: 'UNKNOWN_COLUMN', entityId: 'unknown:metadata_missing', severity: 'warning', reason: '字段未在元数据中找到。', impact: '当前路径可能存在未解析字段。', action: '检查 metadata 或切换 scope。' },
  { id: 'diag_avg', code: 'LOW_CONFIDENCE_LINEAGE', entityId: 'out:avg_order_amount', severity: 'warning', reason: '表达式定位为 approximate。', impact: '只能弱高亮 SQL range。', action: 'View mapping 并人工确认。' },
  { id: 'diag_partial', code: 'PARTIAL_LINEAGE_RESULT', entityId: 'out:group', severity: 'info', reason: '示例未接入真实表基数。', impact: '语义风险为结构推断。', action: '接入 table_grain / unique key。' },
];

export const mappings: EdgeMapping[] = [
  { id: 'map_country', source: 'field:u.country_name', target: 'out:country_name', relation: 'direct', confidence: 'high' },
  { id: 'map_order_cnt', source: 'field:o.order_no', target: 'out:order_cnt', expression: 'expr:valid_order_no', relation: 'aggregate', confidence: 'high' },
  { id: 'map_user_cnt', source: 'field:o.user_id', target: 'out:user_cnt', relation: 'aggregate', confidence: 'high' },
  { id: 'map_gmv', source: 'field:o.order_amount', target: 'out:gmv', relation: 'aggregate', confidence: 'high' },
  { id: 'map_avg_gmv', source: 'out:gmv', target: 'out:avg_order_amount', expression: 'expr:avg_order_amount', relation: 'expression', confidence: 'medium' },
  { id: 'map_avg_order', source: 'out:order_cnt', target: 'out:avg_order_amount', expression: 'expr:avg_order_amount', relation: 'expression', confidence: 'medium' },
];

export const defaultOutputs: SearchItem[] = [
  { itemId: 'out-country', entityId: 'out:country_name', displayName: 'country_name', type: 'output', sub: 'dimension · final select', reason: 'default_output', confidence: 'high' },
  { itemId: 'out-order', entityId: 'out:order_cnt', displayName: 'order_cnt', type: 'output', sub: 'count distinct valid_order_no', reason: 'default_output', confidence: 'high' },
  { itemId: 'out-user', entityId: 'out:user_cnt', displayName: 'user_cnt', type: 'output', sub: 'count distinct user_id', reason: 'default_output', confidence: 'high' },
  { itemId: 'out-gmv', entityId: 'out:gmv', displayName: 'gmv', type: 'output', sub: 'sum(order_amount)', reason: 'default_output', confidence: 'high' },
  { itemId: 'out-avg', entityId: 'out:avg_order_amount', displayName: 'avg_order_amount', type: 'output', sub: 'expression metric · low confidence', reason: 'default_output', confidence: 'medium', warning: true },
];

export const extraSearch: SearchItem[] = [
  { itemId: 'src-order', entityId: 'field:o.order_no', displayName: 'order_no', type: 'source', sub: 'dwd_order_di · order identifier', reason: 'name', confidence: 'high' },
  { itemId: 'src-user', entityId: 'field:o.user_id', displayName: 'user_id', type: 'source', sub: 'dwd_order_di · user identifier', reason: 'name', confidence: 'high' },
  { itemId: 'src-amount', entityId: 'field:o.order_amount', displayName: 'order_amount', type: 'source', sub: 'dwd_order_di · amount', reason: 'name', confidence: 'high' },
  { itemId: 'subq-valid', entityId: 'subq:valid_order_subq', displayName: 'valid_order_subq', type: 'subquery', sub: 'SUBQ · filter · group by path', reason: 'subquery', confidence: 'high' },
  { itemId: 'unknown', entityId: 'unknown:metadata_missing', displayName: 'unknown_col', type: 'diagnostic', sub: 'UNKNOWN_COLUMN', reason: 'diagnostic', confidence: 'low', warning: true },
];

export const paths: Record<string, string[]> = {
  'out:country_name': ['table:dim_user_df', 'cte:order_base', 'subq:valid_order_subq', 'cte:metric_base', 'out:country_name'],
  'out:order_cnt': ['table:dwd_order_di', 'cte:order_base', 'subq:valid_order_subq', 'expr:valid_order_no', 'cte:metric_base', 'out:order_cnt'],
  'out:user_cnt': ['table:dwd_order_di', 'cte:order_base', 'subq:valid_order_subq', 'cte:metric_base', 'out:user_cnt'],
  'out:gmv': ['table:dwd_order_di', 'cte:order_base', 'subq:valid_order_subq', 'cte:metric_base', 'out:gmv'],
  'out:avg_order_amount': ['table:dwd_order_di', 'cte:order_base', 'subq:valid_order_subq', 'cte:metric_base', 'out:gmv', 'out:order_cnt', 'expr:avg_order_amount', 'out:avg_order_amount'],
};

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
  ['snapshot-01-ready-analyze-cta', 'ready 状态 Analyze 主按钮'],
  ['snapshot-02-analyzed-subquery-dependency', '默认子查询依赖图'],
  ['snapshot-03-selected-current-field-path', '当前字段路径'],
  ['snapshot-04-detailpanel-compact-edge-mapping', '选中边映射详情'],
  ['snapshot-05-dirty-reanalyze-stale', 'dirty / stale 可信度提示'],
  ['snapshot-06-failed-error-summary', 'failed 错误摘要'],
  ['snapshot-07-large-graph-subquery-summary', 'large graph 摘要说明'],
  ['snapshot-08-node-taxonomy-100-nodes', '100 节点视觉分类'],
  ['snapshot-09-toolbar-deduplication', '顶部 / 画布工具栏去重'],
  ['snapshot-10-1366-canvas-space-budget', '1366×768 空间预算'],
];

export const milestones = [
  ['M1', 'Base Workbench + PageMode', 'WorkbenchShell / PageModeStore / Splitter'],
  ['M2', 'Analyze + Dirty/Stale Loop', 'AnalyzeClient / TrustStatus / Diagnostics Compact'],
  ['M3', 'Graph Foundation + Adapter', 'ReactFlowAdapter Shell / GraphAdapter / Graph Fact/View/Interaction'],
  ['M4', 'Subquery Dependency + Node Visual', 'SubqueryDependencyViewModel / Node Taxonomy / State Priority'],
  ['M5', 'Search + Field Path', 'SearchBar / Output Capsule / FieldPathApi / PathContextStore'],
  ['M6', 'Detail + Locate + Diagnostics', 'DetailPanel compact / MonacoAdapter / DiagnosticAttentionRule'],
  ['M7', 'UI Hardening + Regression', 'Toolbar Dedup / Primary CTA / Canvas Budget / Snapshots'],
];
