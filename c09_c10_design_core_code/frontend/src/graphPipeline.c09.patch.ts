// C09 graphPipeline patch reference. Merge into existing frontend/src/graphPipeline.ts.

export function mapBackendEdgeType(edgeType: string): string {
  const mapping: Record<string, string> = {
    column_lineage: 'lineage',
    output_column_to_result: 'output',
    expression_dependency: 'dependency',
    expression_to_output: 'derive',
  };
  return mapping[edgeType] || edgeType;
}

export function isVisibleInColumnView(node: { type?: string; data?: { node_type?: string } }): boolean {
  const nodeType = node.data?.node_type || node.type;
  return ['column', 'output_field', 'expression', 'unknown', 'output'].includes(String(nodeType));
}

export function shouldShowQueryResultNode(nodes: Array<{ type?: string; data?: { node_type?: string } }>): boolean {
  return nodes.some((node) => (node.data?.node_type || node.type) === 'output_field');
}

// Layout expectation after C09:
// source column -> expression -> output field -> Query Result
// If there is no expression node, keep C08 layout:
// source column -> output field -> Query Result
