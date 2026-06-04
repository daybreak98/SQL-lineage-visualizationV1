import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { exampleSql } from './data/mockLineage';
import { transitionRenderMode } from './data/selectors';
import { analyzeSql, formatSql, getHealth, listMetadataTables } from './api/client';
import { analysisToGraph } from './graphPipeline';
import type { BackendAnalysisResult, BackendDiagnostic, Diagnostic, GraphEdge, GraphNode, SearchItem, SourceLocation, WorkbenchState } from './types/lineage';
import type { editor as monacoEditor } from 'monaco-editor';
import { revealInEditor } from './components/LineageCanvas/highlight';
import { TopBar } from './components/TopBar';
import { LeftNav } from './components/LeftNav';
import { SqlEditorPanel } from './components/SqlEditorPanel';
import { Splitter } from './components/Splitter';
import { SearchBar } from './components/SearchBar';
import { CanvasToolbar } from './components/CanvasToolbar';
import { LineageCanvas } from './components/LineageCanvas';
import { DetailPanel } from './components/DetailPanel';
import { StatusStrip } from './components/StatusStrip';
import { Drawer } from './components/Drawer';
import { MetadataDialog } from './components/MetadataDialog';

const initialState: WorkbenchState = {
  pageMode: 'empty',
  analysisStatus: 'none',
  trustStatus: 'untrusted',
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
  backendStatus: 'checking...',
  metadataStatus: 'checking...',
};

function normalizeDiagnostic(diagnostic: BackendDiagnostic, index: number): Diagnostic {
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




export default function App() {
  const [sql, setSqlValue] = useState(exampleSql);
  const [dialect, setDialect] = useState('spark');
  const [activeNav, setActiveNav] = useState('workbench');
  const [state, setState] = useState<WorkbenchState>(initialState);
  const [metadataOpen, setMetadataOpen] = useState(false);

  const editorRef = useRef<monacoEditor.IStandaloneCodeEditor | null>(null);

  const handleEditorMounted = useCallback((editor: monacoEditor.IStandaloneCodeEditor) => {
    editorRef.current = editor;
  }, []);

  const handleRevealInEditor = useCallback((entityId: string) => {
    revealInEditor(editorRef.current, entityId, state.sourceLocations, (id) => {
      setState((s) => ({
        ...s,
        backendMessage: `No source location available for entity ${id}. Use the graph view to explore lineage.`,
      }));
    });
  }, [state.sourceLocations]);

  const handleCursorEntityChange = useCallback((entityId: string | null) => {
    if (!entityId) return;
    setState((s) => {
      if (s.selectedEntity === entityId) return s;
      return { ...s, selectedEntity: entityId };
    });
  }, []);

  const refreshBackendStatus = useCallback(async () => {
    try {
      const health = await getHealth();
      setState((s) => ({ ...s, backendStatus: `Backend: ${health.version}` }));
    } catch {
      setState((s) => ({ ...s, backendStatus: 'Backend: offline' }));
    }
  }, []);

  const refreshMetadataStatus = useCallback(async () => {
    try {
      const tables = await listMetadataTables();
      setState((s) => ({ ...s, metadataStatus: `Metadata: ${tables.total} tables` }));
    } catch {
      setState((s) => ({ ...s, metadataStatus: 'Metadata: offline' }));
    }
  }, []);

  useEffect(() => {
    void refreshBackendStatus();
    void refreshMetadataStatus();
  }, [refreshBackendStatus, refreshMetadataStatus]);

  const setSql = (value: string) => {
    setSqlValue(value);
    setState((s) => {
      if (!value.trim()) return { ...s, pageMode: 'empty', analysisStatus: 'none', trustStatus: 'untrusted' };
      if (s.pageMode === 'analyzed' || s.trustStatus === 'trusted') return { ...s, pageMode: 'dirty', trustStatus: 'stale' };
      if (s.pageMode === 'empty') return { ...s, pageMode: 'ready', trustStatus: 'untrusted' };
      return s;
    });
  };

  const onTransition = useCallback((event: string) => {
    setState((s) => {
      const t = transitionRenderMode(s.renderMode, event);
      const patch: Partial<WorkbenchState> = { renderMode: t.mode, lastTransition: t.description };
      if (event === 'CLEAR_SELECTION') {
        patch.selectedOutput = null;
        patch.selectedEntity = 'out:group';
        patch.selectedMapping = null;
      }
      return { ...s, ...patch };
    });
  }, []);

  const onAnalyze = async () => {
    if (!sql.trim()) return;
    setState((s) => ({ ...s, pageMode: 'analyzing', analysisStatus: 'running', trustStatus: 'untrusted' }));
    try {
      const result = await analyzeSql(sql, dialect);
      const { graph, searchItems, colToTables, invalidEdges } = analysisToGraph(result);
      const diagnostics = (result.diagnostics_report?.diagnostics || []).map(normalizeDiagnostic);
      setState((s) => {
        const failed = result.status === 'failed';
        const partial = result.status === 'partial';
        const t = transitionRenderMode(s.renderMode, failed ? 'ANALYZE_FAILED' : 'ANALYZE_SUCCESS');
        return {
          ...s,
          pageMode: failed ? 'failed' : 'analyzed',
          analysisStatus: failed ? 'failed' : partial ? 'partial' : 'success',
          trustStatus: failed ? 'untrusted' : 'trusted',
          selectedOutput: null,
          selectedEntity: 'out:group',
          selectedMapping: null,
          drawerOpen: s.drawerOpen,
          drawerTab: s.drawerTab,
          renderMode: t.mode,
          graphViewMode: result.graph_view_model?.view_mode === 'column'
            ? 'column'
            : result.graph_view_model?.view_mode === 'subquery_dependency'
              ? 'subquery'
              : 'table',
          lastTransition: t.description,
          backendGraph: graph,
          backendSearchItems: searchItems,
          backendDiagnostics: diagnostics,
          colToTables: colToTables,
          backendInvalidEdges: invalidEdges,
          backendMessage: `${result.analysis_id} · ${result.summary?.table_count ?? graph.nodes.length} nodes from backend`,
          positions: {},
        };
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Analyze request failed';
      setState((s) => {
        const t = transitionRenderMode(s.renderMode, 'ANALYZE_FAILED');
        return { ...s, pageMode: 'failed', analysisStatus: 'failed', trustStatus: 'untrusted', drawerOpen: s.drawerOpen, drawerTab: s.drawerTab, renderMode: t.mode, lastTransition: t.description, backendMessage: message, backendDiagnostics: [{ id: 'frontend-api-error', code: 'FRONTEND_API_ERROR', entityId: 'out:group', severity: 'error', reason: message, impact: 'The UI could not call /api/sql/analyze.', action: 'Start the backend service or inspect the API response.' }] };
      });
    }
  };

  const onSelectResult = (item: SearchItem) => {
    setState((s) => {
      let targetEntity = item.entityId;
      if (item.type === 'output' && item.entityId !== 'out:query_result' && s.graphViewMode !== 'column') {
        const ct = s.colToTables?.[item.entityId];
        if (ct && ct.length > 0) {
          const graph = s.backendGraph;
          if (graph) {
            const tableNode = graph.nodes.find(n =>
              n.type === 'table' && ct.some(t => n.entityId.includes(t))
            );
            if (tableNode) targetEntity = tableNode.entityId;
          }
        }
      }
      const event = item.type === 'output' ? 'SELECT_OUTPUT_FIELD' : 'FOCUS_FIELD';
      const t = transitionRenderMode(s.renderMode, event);
      return {
        ...s,
        selectedOutput: item.type === 'output' ? item.entityId : s.selectedOutput,
        selectedEntity: targetEntity,
        selectedMapping: null,
        detailMode: 'compact',
        detailTab: 'summary',
        renderMode: t.mode,
        lastTransition: t.description,
      };
    });
  };

  const setSplit = (split: number) => setState((s) => ({ ...s, split }));

  const workspaceStyle = useMemo(() => ({ ['--split' as string]: `${state.split}%` }), [state.split]);

  return (
    <div className="app" style={workspaceStyle}>
      <TopBar
        state={state}
        dialect={dialect}
        setDialect={setDialect}
        onAnalyze={onAnalyze}
        onFormat={async () => {
          if (!sql.trim()) return;
          try {
            const response = await formatSql(sql, dialect);
            if (response.formatted_sql) {
              setSql(response.formatted_sql);
              setState((s) => ({ ...s, backendMessage: `formatted by /api/sql/format · ${response.dialect}` }));
            }
          } catch (err) {
            const message = err instanceof Error ? err.message : 'Format request failed';
            setState((s) => ({ ...s, backendMessage: message, drawerOpen: s.drawerOpen, drawerTab: s.drawerTab, backendDiagnostics: [{ id: 'format-api-error', code: 'FORMAT_API_ERROR', entityId: 'out:group', severity: 'error', reason: message, impact: 'The UI could not call /api/sql/format.', action: 'Start the backend service or inspect the format endpoint.' }] }));
          }
        }}
        onLoadExample={() => {
          setSqlValue(exampleSql);
          setState((s) => ({ ...s, pageMode: 'ready', analysisStatus: 'none', trustStatus: 'untrusted' }));
        }}
        onMetadata={() => setMetadataOpen(true)}
        onMore={() => setState((s) => ({ ...s, drawerOpen: !s.drawerOpen, drawerTab: 'more' }))}
      />
      <div className="body">
        <LeftNav active={activeNav} onOpen={(tab) => { setActiveNav(tab); if (tab !== 'workbench') setState((s) => ({ ...s, drawerOpen: true, drawerTab: tab })); }} />
        <main className="app-main">
          <div className="workspace" id="workspace">
            <SqlEditorPanel sql={sql} setSql={setSql} state={state} dialect={dialect} sourceLocations={state.sourceLocations} onEditorMounted={handleEditorMounted} onCursorEntityChange={handleCursorEntityChange} />
            <Splitter split={state.split} setSplit={setSplit} />
            <section className="canvas-panel">
              <SearchBar state={state} setState={setState} onSelectResult={onSelectResult} />
              <CanvasToolbar state={state} setState={setState} onTransition={onTransition} />
              <LineageCanvas state={state} setState={setState} onNodeDoubleClick={handleRevealInEditor} />
              <DetailPanel state={state} setState={setState} onLocateSql={handleRevealInEditor} />
            </section>
          </div>
          <StatusStrip state={state} setState={setState} />
          <Drawer state={state} setState={setState} />
        </main>
      </div>
      <MetadataDialog open={metadataOpen} onClose={() => setMetadataOpen(false)} onImported={refreshMetadataStatus} />
    </div>
  );
}
