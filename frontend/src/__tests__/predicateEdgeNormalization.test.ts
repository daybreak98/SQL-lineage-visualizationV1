import { describe, expect, it } from 'vitest';
import { normalizeBackendGraph } from '../graphPipeline';
import type { BackendAnalysisResult } from '../types/lineage';

describe('predicate edge normalization', () => {
  it('preserves predicate and join semantics from the backend graph', () => {
    const result: BackendAnalysisResult = {
      analysis_id: 'predicate-edge-test',
      status: 'success',
      graph_view_model: {
        nodes: [
          {
            id: 'physical_column:orders.status',
            node_type: 'physical_column',
            label: 'orders.status',
          },
          {
            id: 'predicate:where:query_result:final:1',
            node_type: 'expression',
            label: "WHERE: status = 'PAID'",
          },
          {
            id: 'predicate:join:query_result:final:1',
            node_type: 'expression',
            label: 'JOIN: orders.customer_id = customers.id',
          },
          {
            id: 'clause:group_by:query_result:final:1',
            node_type: 'expression',
            label: 'GROUP BY: region',
          },
          {
            id: 'clause:order_by:query_result:final:1',
            node_type: 'expression',
            label: 'ORDER BY: created_at',
          },
          {
            id: 'query_result:final',
            node_type: 'output',
            label: 'Query Result',
          },
        ],
        edges: [
          {
            id: 'predicate-input',
            source: 'physical_column:orders.status',
            target: 'predicate:where:query_result:final:1',
            edge_type: 'predicate_dependency',
          },
          {
            id: 'predicate-effect',
            source: 'predicate:where:query_result:final:1',
            target: 'query_result:final',
            edge_type: 'predicate_effect',
          },
          {
            id: 'join-input',
            source: 'physical_column:orders.status',
            target: 'predicate:join:query_result:final:1',
            edge_type: 'join_dependency',
          },
          {
            id: 'join-effect',
            source: 'predicate:join:query_result:final:1',
            target: 'query_result:final',
            edge_type: 'join_effect',
          },
          {
            id: 'group-input',
            source: 'physical_column:orders.status',
            target: 'clause:group_by:query_result:final:1',
            edge_type: 'group_dependency',
          },
          {
            id: 'group-effect',
            source: 'clause:group_by:query_result:final:1',
            target: 'query_result:final',
            edge_type: 'group_effect',
          },
          {
            id: 'order-input',
            source: 'physical_column:orders.status',
            target: 'clause:order_by:query_result:final:1',
            edge_type: 'order_dependency',
          },
          {
            id: 'order-effect',
            source: 'clause:order_by:query_result:final:1',
            target: 'query_result:final',
            edge_type: 'order_effect',
          },
        ],
      },
    };

    const graph = normalizeBackendGraph(result);
    const edgeTypes = Object.fromEntries(
      graph.edges.map((edge) => [edge.id, edge.type]),
    );

    expect(edgeTypes).toEqual({
      'predicate-input': 'expr',
      'predicate-effect': 'expr',
      'join-input': 'join',
      'join-effect': 'join',
      'group-input': 'expr',
      'group-effect': 'expr',
      'order-input': 'expr',
      'order-effect': 'expr',
    });
    expect(graph.invalidEdges).toEqual([]);
  });
});
