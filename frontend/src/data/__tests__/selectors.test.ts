import { describe, it, expect } from 'vitest';
import { subqueryNodes, subqueryEdges, paths, diagnostics } from '../mockLineage';
import { visibleGraph } from '../../graphPipeline';
import {
  buildPathContext,
  currentEntitySet,
  diagnosticsOf,
  entityName,
  entityOf,
  deriveAttention,
  fieldNodes,
  fieldEdges,
  transitionRenderMode,
} from '../selectors';
import type { WorkbenchState } from '../../types/lineage';

function baseState(overrides: Partial<WorkbenchState> = {}): WorkbenchState {
  return {
    pageMode: 'analyzed',
    analysisStatus: 'success',
    trustStatus: 'trusted',
    selectedOutput: null,
    selectedEntity: 'out:group',
    selectedMapping: null,
    renderMode: 'subquery_dependency',
    graphViewMode: 'table',
    detailMode: 'compact',
    detailTab: 'summary',
    drawerOpen: false,
    drawerTab: 'diagnostics',
    split: 28,
    query: '',
    scope: 'all',
    large: false,
    positions: {},
    ...overrides,
  };
}

describe('selectors', () => {
  describe('visibleGraph', () => {
    it('returns an empty graph for semantics view mode without backendGraph', () => {
      const state = baseState({ graphViewMode: 'semantics' });
      const graph = visibleGraph(state);
      expect(graph.nodes).toEqual([]);
      expect(graph.edges).toEqual([]);
    });

    it('returns backendGraph when present for semantics view mode', () => {
      const backendGraph = { nodes: [subqueryNodes[0]], edges: [subqueryEdges[0]] };
      const state = baseState({ graphViewMode: 'semantics', backendGraph });
      const graph = visibleGraph(state);
      expect(graph.nodes).toEqual(backendGraph.nodes);
      expect(graph.edges).toEqual(backendGraph.edges);
    });

    it('returns an empty graph for column view mode without backendGraph', () => {
      const state = baseState({ graphViewMode: 'column', selectedOutput: 'out:order_cnt' });
      const graph = visibleGraph(state);
      expect(graph.nodes).toEqual([]);
      expect(graph.edges).toEqual([]);
    });

    it('returns an empty graph for column view when backend has only structure nodes', () => {
      const backendGraph = {
        nodes: [
          { id: 'physical_table:dwd_order_di', entityId: 'physical_table:dwd_order_di', type: 'table' as const, label: 'dwd_order_di', x: 0, y: 0 },
          { id: 'cte:metric_base', entityId: 'cte:metric_base', type: 'cte' as const, label: 'metric_base', x: 160, y: 0 },
          { id: 'query_result:final', entityId: 'query_result:final', type: 'output' as const, label: 'Query Result', x: 320, y: 0 },
        ],
        edges: [
          { id: 'e1', source: 'physical_table:dwd_order_di', target: 'cte:metric_base', type: 'table' as const },
          { id: 'e2', source: 'cte:metric_base', target: 'query_result:final', type: 'output' as const },
        ],
      };
      const graph = visibleGraph(baseState({ graphViewMode: 'column', backendGraph }));

      expect(graph.nodes).toEqual([]);
      expect(graph.edges).toEqual([]);
    });

    it('returns table, CTE, subquery and output nodes in subquery view mode', () => {
      const state = baseState({
        graphViewMode: 'subquery',
        backendGraph: { nodes: subqueryNodes, edges: subqueryEdges },
      });
      const graph = visibleGraph(state);
      for (const node of graph.nodes) {
        expect(['table', 'cte', 'subquery', 'output']).toContain(node.type);
      }
      expect(graph.nodes.some(node => node.type === 'cte' || node.type === 'subquery')).toBe(true);
    });

    it('returns only table and output nodes in table view mode', () => {
      const state = baseState({
        graphViewMode: 'table',
        backendGraph: { nodes: subqueryNodes, edges: subqueryEdges },
      });
      const graph = visibleGraph(state);
      for (const node of graph.nodes) {
        expect(['table', 'output']).toContain(node.type);
      }
      // Should have fewer nodes than full subquery graph (filters out CTE/subquery)
      expect(graph.nodes.length).toBeLessThan(subqueryNodes.length);
    });

    it('recomputes compact positions for table view nodes', () => {
      const backendGraph = {
        nodes: [
          { id: 'physical_table:dwd_order_di', entityId: 'physical_table:dwd_order_di', type: 'table' as const, label: 'dwd_order_di', x: 72, y: 72 },
          { id: 'physical_table:dim_user_df', entityId: 'physical_table:dim_user_df', type: 'table' as const, label: 'dim_user_df', x: 72, y: 134 },
          { id: 'cte:metric_base', entityId: 'cte:metric_base', type: 'cte' as const, label: 'metric_base', x: 582, y: 72 },
          { id: 'query_result:final', entityId: 'query_result:final', type: 'output' as const, label: 'Query Result', x: 752, y: 72 },
        ],
        edges: [
          { id: 'e1', source: 'physical_table:dwd_order_di', target: 'cte:metric_base', type: 'table' as const },
          { id: 'e2', source: 'physical_table:dim_user_df', target: 'cte:metric_base', type: 'table' as const },
          { id: 'e3', source: 'cte:metric_base', target: 'query_result:final', type: 'output' as const },
        ],
      };
      const graph = visibleGraph(baseState({ graphViewMode: 'table', backendGraph }));
      const output = graph.nodes.find(node => node.type === 'output');
      const rightMostTableX = Math.max(...graph.nodes.filter(node => node.type === 'table').map(node => node.x));

      expect(output?.x).toBe(310);
      expect(output!.x - rightMostTableX).toBeLessThan(260);
      expect(graph.edges.filter(edge => edge.target === output?.entityId)).toHaveLength(2);
    });
  });

  describe('buildPathContext', () => {
    it('returns idle when no output selected', () => {
      const state = baseState({ selectedOutput: null });
      const pc = buildPathContext(state);
      expect(pc.status).toBe('idle');
      expect(pc.display).toBe('Choose output');
    });

    it('returns ready with correct display for selected output', () => {
      const state = baseState({ selectedOutput: 'out:order_cnt' });
      const pc = buildPathContext(state);
      expect(pc.status).toBe('ready');
      expect(pc.display).toBe('order_cnt');
      expect(pc.nodes).toBe(paths['out:order_cnt']?.length ?? 0);
    });

    it('returns stale when trustStatus is stale', () => {
      const state = baseState({ selectedOutput: 'out:order_cnt', trustStatus: 'stale' });
      const pc = buildPathContext(state);
      expect(pc.status).toBe('stale');
    });

    it('returns partial when analysisStatus is partial', () => {
      const state = baseState({ selectedOutput: 'out:order_cnt', analysisStatus: 'partial' });
      const pc = buildPathContext(state);
      expect(pc.status).toBe('partial');
    });

    it('returns low_confidence for avg_order_amount output', () => {
      const state = baseState({ selectedOutput: 'out:avg_order_amount' });
      const pc = buildPathContext(state);
      expect(pc.status).toBe('low_confidence');
      expect(pc.confidence).toBe('medium');
    });
  });

  describe('currentEntitySet', () => {
    it('returns entity IDs for semantics view mode', () => {
      const state = baseState({
        graphViewMode: 'semantics',
        backendGraph: { nodes: subqueryNodes, edges: subqueryEdges },
      });
      const set = currentEntitySet(state);
      for (const node of subqueryNodes) {
        expect(set.has(node.entityId)).toBe(true);
      }
      expect(set.size).toBe(subqueryNodes.length);
    });

    it('returns empty entity set for column view mode without backendGraph', () => {
      const state = baseState({ graphViewMode: 'column', selectedOutput: 'out:order_cnt' });
      const set = currentEntitySet(state);
      expect(set.size).toBe(0);
    });

    it('returns empty entity set when no output selected in column view without backendGraph', () => {
      const state = baseState({ graphViewMode: 'column', selectedOutput: null });
      const set = currentEntitySet(state);
      expect(set.size).toBe(0);
    });
  });

  describe('diagnosticsOf', () => {
    it('returns diagnostics for a matching entity', () => {
      const result = diagnosticsOf('out:avg_order_amount');
      expect(result.length).toBeGreaterThan(0);
      expect(result.every((d) => d.entityId === 'out:avg_order_amount')).toBe(true);
    });

    it('returns empty array for entity with no diagnostics', () => {
      const result = diagnosticsOf('table:dwd_order_di');
      expect(result).toEqual([]);
    });

    it('returns empty array for null entityId', () => {
      expect(diagnosticsOf(null)).toEqual([]);
      expect(diagnosticsOf(undefined)).toEqual([]);
    });
  });

  describe('entityName', () => {
    it('returns entity name for valid id', () => {
      expect(entityName('table:dwd_order_di')).toBe('dwd_order_di');
      expect(entityName('out:order_cnt')).toBe('order_cnt');
    });

    it('returns dash for null/empty id', () => {
      expect(entityName(null)).toBe('-');
      expect(entityName(undefined)).toBe('-');
    });
  });

  describe('entityOf', () => {
    it('returns entity for valid id', () => {
      const entity = entityOf('table:dwd_order_di');
      expect(entity).toBeDefined();
      expect(entity!.name).toBe('dwd_order_di');
    });

    it('returns undefined for unknown id', () => {
      expect(entityOf('nonexistent')).toBeUndefined();
    });

    it('returns undefined for null/empty id', () => {
      expect(entityOf(null)).toBeUndefined();
      expect(entityOf(undefined)).toBeUndefined();
    });
  });

  describe('deriveAttention', () => {
    it('returns empty_guide for empty pageMode', () => {
      const [slot, _, category] = deriveAttention(baseState({ pageMode: 'empty' }));
      expect(slot).toBe('empty_guide');
      expect(category).toBe('page_mode');
    });

    it('returns analyze for ready pageMode', () => {
      const [slot] = deriveAttention(baseState({ pageMode: 'ready' }));
      expect(slot).toBe('analyze');
    });

    it('returns error_summary for failed pageMode', () => {
      const [slot, _, category] = deriveAttention(baseState({ pageMode: 'failed' }));
      expect(slot).toBe('error_summary');
      expect(category).toBe('diagnostic');
    });

    it('returns current_path when output is selected', () => {
      const [slot, _, category] = deriveAttention(baseState({ selectedOutput: 'out:order_cnt' }));
      expect(slot).toBe('current_path');
      expect(category).toBe('path_context');
    });
  });

  describe('transitionRenderMode', () => {
    it('transitions to subquery_dependency on ANALYZE_SUCCESS', () => {
      const result = transitionRenderMode('subquery_dependency', 'ANALYZE_SUCCESS');
      expect(result.mode).toBe('subquery_dependency');
    });

    it('transitions to current_field_path on SELECT_OUTPUT_FIELD', () => {
      const result = transitionRenderMode('subquery_dependency', 'SELECT_OUTPUT_FIELD');
      expect(result.mode).toBe('current_field_path');
    });

    it('returns unchanged for unknown event', () => {
      const result = transitionRenderMode('subquery_dependency', 'UNKNOWN_EVENT');
      expect(result.mode).toBe('subquery_dependency');
      expect(result.description).toContain('unchanged');
    });
  });
});
