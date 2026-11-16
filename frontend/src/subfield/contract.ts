export interface Position { start: number; end: number }
export interface Port { statement: number; scope: string; slot: number }
export interface RecordRow {
  [key: string]: unknown;
  position?: Position | null;
  output?: string;
  role?: string;
}
export interface Result {
  uses: RecordRow[];
  mappings: RecordRow[];
  unknowns: RecordRow[];
  coverage?: { parsed?: boolean; partial?: boolean; recovered?: number; complete?: boolean };
  generators?: unknown;
  windows?: unknown;
  row_selections?: unknown;
  review?: unknown;
}
export interface PathItem {
  id: string;
  input: { source: string; column: string; path: string; path_tokens?: {kind: string; value?: string | number}[] };
  uses: RecordRow[];
}
export interface GraphNode { key: string; lane: number; label: string; display?: string; root?: boolean; kind?: 'path' | 'unknown'; uncertain: boolean; evidence: Set<RecordRow> }
export interface GraphEdge { from: string; to: string; uncertain: boolean; evidence: Set<RecordRow> }
export interface Graph { nodes: GraphNode[]; edges: GraphEdge[]; lanes?: string[] }
