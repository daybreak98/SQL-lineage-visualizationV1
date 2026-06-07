// C09 TypeScript type reference. Merge into existing frontend/src/types/*.ts.

export type ConfidenceLevel = 'high' | 'medium' | 'low';

export interface MetricSemantics {
  name: string;
  entity_id?: string | null;
  expression: string;
  depends_on: string[];
  aggregate_functions: string[];
  operators: string[];
  function_names?: string[];
  description?: string | null;
  evidence?: Record<string, unknown>;
  confidence_level?: ConfidenceLevel;
}

export interface SemanticsReport {
  metrics: MetricSemantics[];
  filters?: Array<Record<string, unknown>>;
  result_grain?: string | null;
  notes?: string[];
}

export interface GraphNodeData {
  node_type?: string;
  name?: string;
  expression?: string;
  depends_on?: string[];
  aggregate_functions?: string[];
  operators?: string[];
  function_names?: string[];
  description?: string;
  [key: string]: unknown;
}

export interface GraphNode {
  id: string;
  entity_id?: string;
  type: string;
  label?: string;
  data?: GraphNodeData;
}

export interface AnalysisResultC09Patch {
  semantics_report?: SemanticsReport;
}
