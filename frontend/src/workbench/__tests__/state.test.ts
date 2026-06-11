import { describe, expect, it } from 'vitest';
import type { BackendAnalysisResult, SearchItem } from '../../types/lineage';
import {
  applySearchSelection,
  applySqlDraftChange,
  buildAnalyzeFailureState,
  buildAnalyzeRunningState,
  buildAnalyzeSuccessState,
  initialWorkbenchState,
} from '../state';

describe('workbench state helpers', () => {
  it('keeps the bottom detail panel closed by default', () => {
    expect(initialWorkbenchState.detailMode).toBe('collapsed');
  });

  it('marks analyzed workbench as dirty after sql edit', () => {
    const next = applySqlDraftChange(
      { ...initialWorkbenchState, pageMode: 'analyzed', trustStatus: 'trusted' },
      'select * from t',
    );

    expect(next.pageMode).toBe('dirty');
    expect(next.trustStatus).toBe('stale');
  });

  it('builds analyze running state', () => {
    const next = buildAnalyzeRunningState(initialWorkbenchState);

    expect(next.pageMode).toBe('analyzing');
    expect(next.analysisStatus).toBe('running');
    expect(next.trustStatus).toBe('untrusted');
  });

  it('builds analyze success state with normalized graph payload', () => {
    const result: BackendAnalysisResult = {
      analysis_id: 'analysis:test',
      status: 'success',
      graph_view_model: {
        view_mode: 'subquery_dependency',
        nodes: [
          { id: 'physical_table:dwd_order_di', node_type: 'table', label: 'dwd_order_di' },
          { id: 'cte:order_base', node_type: 'cte', label: 'order_base' },
          { id: 'query_result:final', node_type: 'output', label: 'Query Result' },
        ],
        edges: [
          {
            id: 'edge:table-cte',
            source: 'physical_table:dwd_order_di',
            target: 'cte:order_base',
            edge_type: 'table_to_cte',
          },
          {
            id: 'edge:cte-out',
            source: 'cte:order_base',
            target: 'query_result:final',
            edge_type: 'cte_to_result',
          },
        ],
      },
      diagnostics_report: { diagnostics: [] },
      summary: { table_count: 3 },
    };

    const next = buildAnalyzeSuccessState(
      { ...initialWorkbenchState, detailMode: 'compact' },
      result,
    );

    expect(next.pageMode).toBe('analyzed');
    expect(next.analysisStatus).toBe('success');
    expect(next.trustStatus).toBe('trusted');
    expect(next.detailMode).toBe('collapsed');
    expect(next.graphViewMode).toBe('subquery');
    expect(next.backendGraph?.nodes).toHaveLength(3);
    expect(next.backendSearchItems?.length).toBeGreaterThan(0);
    expect(next.backendMessage).toContain('analysis:test');
  });

  it('builds analyze failure state with frontend diagnostic', () => {
    const next = buildAnalyzeFailureState(initialWorkbenchState, 'network error');

    expect(next.pageMode).toBe('failed');
    expect(next.analysisStatus).toBe('failed');
    expect(next.backendDiagnostics?.[0].code).toBe('FRONTEND_API_ERROR');
  });

  it('selects output search result and transitions render mode', () => {
    const item: SearchItem = {
      itemId: 'search-output-1',
      entityId: 'out:order_cnt',
      displayName: 'order_cnt',
      type: 'output',
      sub: 'from: dwd_order_di',
      reason: 'lineage edge',
      confidence: 'high',
    };

    const next = applySearchSelection(
      {
        ...initialWorkbenchState,
        pageMode: 'analyzed',
        analysisStatus: 'success',
        trustStatus: 'trusted',
        backendGraph: {
          nodes: [
            { id: 'physical_table:dwd_order_di', entityId: 'physical_table:dwd_order_di', type: 'table', label: 'dwd_order_di', x: 0, y: 0 },
            { id: 'out:order_cnt', entityId: 'out:order_cnt', type: 'output_field', label: 'order_cnt', x: 0, y: 0 },
          ],
          edges: [],
        },
        colToTables: { 'out:order_cnt': ['dwd_order_di'] },
      },
      item,
    );

    expect(next.selectedOutput).toBe('out:order_cnt');
    expect(next.selectedEntity).toBe('physical_table:dwd_order_di');
    expect(next.detailMode).toBe('compact');
    expect(next.renderMode).toBe('current_field_path');
  });
});
