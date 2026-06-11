import { analysisToGraph } from '../graphPipeline';
import { transitionRenderMode } from '../data/selectors';
import type { BackendAnalysisResult, BackendDiagnostic, Diagnostic, SearchItem, WorkbenchState } from '../types/lineage';

export const initialWorkbenchState: WorkbenchState = {
  pageMode: 'empty',
  analysisStatus: 'none',
  trustStatus: 'untrusted',
  selectedOutput: null,
  selectedEntity: 'out:group',
  selectedMapping: null,
  renderMode: 'subquery_dependency',
  graphViewMode: 'table',
  detailMode: 'collapsed',
  detailTab: 'summary',
  drawerOpen: false,
  drawerTab: 'diagnostics',
  split: 28,
  query: '',
  scope: 'all',
  large: false,
  positions: {},
  backendStatus: 'checking...',
  metadataStatus: 'checking...',
};

export function normalizeWorkbenchDiagnostic(diagnostic: BackendDiagnostic, index: number): Diagnostic {
  return {
    id: diagnostic.diagnostic_id || `backend-diag-${index}`,
    code: diagnostic.code,
    entityId: diagnostic.related_entity_ids?.[0] || 'out:group',
    severity: diagnostic.level,
    reason: diagnostic.message,
    impact: diagnostic.details ? JSON.stringify(diagnostic.details) : 'Backend diagnostic',
    action: diagnostic.suggestion || 'Review SQL, metadata, or parser diagnostics.',
  };
}

export function applySqlDraftChange(state: WorkbenchState, value: string): WorkbenchState {
  if (!value.trim()) {
    return { ...state, pageMode: 'empty', analysisStatus: 'none', trustStatus: 'untrusted' };
  }
  if (state.pageMode === 'analyzed' || state.trustStatus === 'trusted') {
    return { ...state, pageMode: 'dirty', trustStatus: 'stale' };
  }
  if (state.pageMode === 'empty') {
    return { ...state, pageMode: 'ready', trustStatus: 'untrusted' };
  }
  return state;
}

export function buildAnalyzeRunningState(state: WorkbenchState): WorkbenchState {
  return { ...state, pageMode: 'analyzing', analysisStatus: 'running', trustStatus: 'untrusted' };
}

export function buildAnalyzeSuccessState(state: WorkbenchState, result: BackendAnalysisResult): WorkbenchState {
  const { graph, searchItems, colToTables, invalidEdges } = analysisToGraph(result);
  const diagnostics = (result.diagnostics_report?.diagnostics || []).map(normalizeWorkbenchDiagnostic);
  const failed = result.status === 'failed';
  const partial = result.status === 'partial';
  const transition = transitionRenderMode(state.renderMode, failed ? 'ANALYZE_FAILED' : 'ANALYZE_SUCCESS');

  return {
    ...state,
    pageMode: failed ? 'failed' : 'analyzed',
    analysisStatus: failed ? 'failed' : partial ? 'partial' : 'success',
    trustStatus: failed ? 'untrusted' : 'trusted',
    selectedOutput: null,
    selectedEntity: 'out:group',
    selectedMapping: null,
    detailMode: 'collapsed',
    detailTab: 'summary',
    drawerOpen: state.drawerOpen,
    drawerTab: state.drawerTab,
    renderMode: transition.mode,
    graphViewMode: result.graph_view_model?.view_mode === 'column'
      ? 'column'
      : result.graph_view_model?.view_mode === 'subquery_dependency'
        ? 'subquery'
        : 'table',
    lastTransition: transition.description,
    backendGraph: graph,
    backendSearchItems: searchItems,
    backendDiagnostics: diagnostics,
    sourceLocations: result.source_locations ?? {},
    semanticsReport: result.semantics_report ?? undefined,
    colToTables,
    backendInvalidEdges: invalidEdges,
    backendMessage: `${result.analysis_id} | ${result.summary?.table_count ?? graph.nodes.length} nodes from backend`,
    positions: {},
  };
}

export function buildAnalyzeFailureState(state: WorkbenchState, message: string): WorkbenchState {
  const transition = transitionRenderMode(state.renderMode, 'ANALYZE_FAILED');

  return {
    ...state,
    pageMode: 'failed',
    analysisStatus: 'failed',
    trustStatus: 'untrusted',
    drawerOpen: state.drawerOpen,
    drawerTab: state.drawerTab,
    renderMode: transition.mode,
    lastTransition: transition.description,
    backendMessage: message,
    backendDiagnostics: [{
      id: 'frontend-api-error',
      code: 'FRONTEND_API_ERROR',
      entityId: 'out:group',
      severity: 'error',
      reason: message,
      impact: 'The UI could not call /api/sql/analyze.',
      action: 'Start the backend service or inspect the API response.',
    }],
  };
}

export function applySearchSelection(state: WorkbenchState, item: SearchItem): WorkbenchState {
  let targetEntity = item.entityId;
  if (item.type === 'output' && item.entityId !== 'out:query_result' && state.graphViewMode !== 'column') {
    const candidateTables = state.colToTables?.[item.entityId];
    if (candidateTables && candidateTables.length > 0 && state.backendGraph) {
      const tableNode = state.backendGraph.nodes.find(
        (node) => node.type === 'table' && candidateTables.some((table) => node.entityId.includes(table)),
      );
      if (tableNode) targetEntity = tableNode.entityId;
    }
  }

  const event = item.type === 'output' ? 'SELECT_OUTPUT_FIELD' : 'FOCUS_FIELD';
  const transition = transitionRenderMode(state.renderMode, event);

  return {
    ...state,
    selectedOutput: item.type === 'output' ? item.entityId : state.selectedOutput,
    selectedEntity: targetEntity,
    selectedMapping: null,
    detailMode: 'compact',
    detailTab: 'summary',
    renderMode: transition.mode,
    lastTransition: transition.description,
  };
}
