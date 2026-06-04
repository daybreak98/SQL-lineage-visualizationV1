export type PageMode = 'empty' | 'ready' | 'analyzing' | 'analyzed' | 'dirty' | 'failed';
export type AnalysisStatus = 'none' | 'running' | 'success' | 'partial' | 'failed';
export type TrustStatus = 'trusted' | 'stale' | 'untrusted';
export type GraphRenderMode = 'subquery_dependency' | 'current_field_path' | 'focus_field' | 'semantic_mode' | 'large_graph' | 'full_graph_preview';
export type GraphViewMode = 'table' | 'subquery' | 'column' | 'expression' | 'semantics' | 'diagnostics';
export type DetailTab = 'summary' | 'mapping' | 'source' | 'diagnostics' | 'semantics';
export type DetailMode = 'collapsed' | 'compact' | 'expanded';

export interface Entity {
  id: string;
  type: 'table' | 'cte' | 'subquery' | 'output_group' | 'output_field' | 'column' | 'expression' | 'unknown' | 'join';
  name: string;
  comment: string;
}

export interface SourceLocation {
  entityId: string;
  line: number;
  col: number;
  rangeType: 'exact' | 'approximate' | 'unavailable';
  raw: string;
}

export interface Diagnostic {
  id: string;
  code: string;
  entityId: string;
  severity: 'info' | 'warning' | 'error';
  reason: string;
  impact: string;
  action: string;
}

export interface EdgeMapping {
  id: string;
  source: string;
  target: string;
  expression?: string;
  relation: 'direct' | 'aggregate' | 'expression' | 'join_dependency';
  confidence: 'high' | 'medium' | 'low';
}

export interface SearchItem {
  itemId: string;
  entityId: string;
  displayName: string;
  type: 'output' | 'source' | 'subquery' | 'expression' | 'diagnostic';
  sub: string;
  reason: string;
  confidence: 'high' | 'medium' | 'low';
  warning?: boolean;
}

export interface GraphNode {
  id: string;
  entityId: string;
  type: 'table' | 'column' | 'cte' | 'subquery' | 'output' | 'output_field' | 'expression' | 'unknown';
  label: string;
  tag?: string;
  x: number;
  y: number;
  pinned?: boolean;
  ordinal?: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: 'table' | 'cte' | 'subq' | 'output' | 'expr' | 'join' | 'projection' | 'alias' | 'unknown';
  mapping?: string;
  synthetic?: boolean;
}

export interface BackendDiagnostic {
  diagnostic_id?: string;
  code: string;
  level: 'info' | 'warning' | 'error';
  message: string;
  suggestion?: string | null;
  related_entity_ids?: string[];
  details?: Record<string, unknown>;
}

export interface FormatSqlResponse {
  status: 'success' | 'partial' | 'failed';
  dialect: string;
  formatted_sql: string | null;
  diagnostics: BackendDiagnostic[];
}

export interface BackendAnalysisResult {
  schema_version?: string;
  analysis_id: string;
  status: 'success' | 'partial' | 'failed';
  confidence_level?: 'high' | 'medium' | 'low' | 'unknown';
  confidence_reasons?: string[];
  elapsed_ms?: number;
  dialect?: string;
  normalized_sql?: string | null;
  tables_extracted?: string[];
  columns_extracted?: string[];
  stage_statuses?: Array<{
    stage: string;
    status: 'success' | 'partial' | 'failed' | 'skipped';
    elapsed_ms: number;
    diagnostic_codes: string[];
    message?: string | null;
  }>;
  unsupported_features?: string[];
  diagnostics_report?: {
    diagnostics?: BackendDiagnostic[];
    error_count?: number;
    warning_count?: number;
    info_count?: number;
  };
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
      data?: Record<string, unknown>;
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
  summary?: Record<string, number>;
}

export interface MetadataPayload {
  schema_version: string;
  metadata_version: string;
  case_sensitive?: boolean;
  default_catalog?: string;
  default_schema?: string;
  source_name?: string | null;
  tables: Array<{
    catalog?: string;
    schema?: string;
    name: string;
    comment?: string | null;
    table_type?: string;
    columns: Array<{
      name: string;
      data_type?: string;
      comment?: string | null;
      ordinal?: number | null;
      is_partition?: boolean;
      nullable?: boolean | null;
    }>;
  }>;
}

export interface MetadataImportResult {
  status: 'preview_ready' | 'committed' | 'failed';
  import_batch_id: string | null;
  metadata_version: string;
  changes: Array<{
    change_type: 'added' | 'updated' | 'unchanged' | 'stale_candidate' | 'conflict';
    object_type: 'table' | 'column';
    object_ref: { catalog: string; schema: string; table: string; column?: string | null };
    message?: string | null;
  }>;
  diagnostics: BackendDiagnostic[];
  summary: Record<string, number>;
}

export interface MetadataListResponse {
  tables?: Array<Record<string, unknown>>;
  columns?: Array<Record<string, unknown>>;
  total: number;
}

export interface PathContext {
  status: 'idle' | 'ready' | 'partial' | 'stale' | 'low_confidence';
  display: string;
  nodes: number;
  mappings: number;
  warnings: number;
  confidence: 'high' | 'medium' | 'unknown';
}

export interface WorkbenchState {
  pageMode: PageMode;
  analysisStatus: AnalysisStatus;
  trustStatus: TrustStatus;
  selectedOutput: string | null;
  selectedEntity: string;
  selectedMapping: string | null;
  renderMode: GraphRenderMode;
  graphViewMode: GraphViewMode;
  detailMode: DetailMode;
  detailTab: DetailTab;
  drawerOpen: boolean;
  drawerTab: string;
  split: number;
  query: string;
  scope: string;
  large: boolean;
  lastTransition?: string;
  positions: Record<string, { x: number; y: number }>;
  sourceLocations?: Record<string, SourceLocation>;
  backendGraph?: { nodes: GraphNode[]; edges: GraphEdge[] };
  backendSearchItems?: SearchItem[];
  backendDiagnostics?: Diagnostic[];
  backendMessage?: string;
  backendStatus?: string;
  metadataStatus?: string;
  colToTables?: Record<string, string[]>;
  backendInvalidEdges?: GraphEdge[];
}
