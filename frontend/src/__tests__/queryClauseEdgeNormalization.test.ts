import { describe, expect, it } from 'vitest';
import { normalizeBackendGraph } from '../graphPipeline';
import type { BackendAnalysisResult } from '../types/lineage';

describe('Spark query clause edge normalization', () => {
  it('keeps distribute, sort, and cluster edges as expression semantics', () => {
    const kinds = ['distribute', 'sort', 'cluster'] as const;
    const nodes = [
      {
        id: 'physical_column:events.tenant_id',
        node_type: 'physical_column',
        label: 'events.tenant_id',
      },
      {
        id: 'query_result:final',
        node_type: 'output',
        label: 'Query Result',
      },
      ...kinds.map((kind) => ({
        id: `clause:${kind}_by:query_result:final:1`,
        node_type: 'expression',
        label: `${kind.toUpperCase()} BY`,
      })),
    ];
    const edges = kinds.flatMap((kind) => {
      const clauseId = `clause:${kind}_by:query_result:final:1`;
      return [
        {
          id: `${kind}-input`,
          source: 'physical_column:events.tenant_id',
          target: clauseId,
          edge_type: `${kind}_dependency`,
        },
        {
          id: `${kind}-effect`,
          source: clauseId,
          target: 'query_result:final',
          edge_type: `${kind}_effect`,
        },
      ];
    });
    const result: BackendAnalysisResult = {
      analysis_id: 'query-clause-edge-test',
      status: 'success',
      graph_view_model: { nodes, edges },
    };

    const graph = normalizeBackendGraph(result);

    expect(graph.invalidEdges).toEqual([]);
    expect(graph.edges).toHaveLength(6);
    expect(graph.edges.every((edge) => edge.type === 'expr')).toBe(true);
  });
});
