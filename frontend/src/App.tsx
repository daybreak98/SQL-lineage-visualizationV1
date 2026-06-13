import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { editor as monacoEditor } from 'monaco-editor';
import { analyzeSql, formatSql, getHealth, listMetadataTables } from './api/client';
import { CanvasToolbar } from './components/CanvasToolbar';
import { ConvertTopBar } from './components/ConvertTopBar';
import { DetailPanel } from './components/DetailPanel';
import { Drawer } from './components/Drawer';
import { LeftNav } from './components/LeftNav';
import { LineageCanvas } from './components/LineageCanvas';
import { revealInEditor } from './components/LineageCanvas/highlight';
import { MetadataDialog } from './components/MetadataDialog';
import { SearchBar } from './components/SearchBar';
import { Splitter } from './components/Splitter';
import { SqlEditorPanel } from './components/SqlEditorPanel';
import { StatusStrip } from './components/StatusStrip';
import { TopBar } from './components/TopBar';
import { exampleSql } from './data/exampleSql';
import { transitionRenderMode } from './data/selectors';
import { DebugPage } from './pages/DebugPage';
import { DialectConvertPage } from './pages/DialectConvertPage';
import type { SearchItem, WorkbenchState } from './types/lineage';
import {
  applySearchSelection,
  applySqlDraftChange,
  buildAnalyzeFailureState,
  buildAnalyzeRunningState,
  buildAnalyzeSuccessState,
  initialWorkbenchState,
} from './workbench/state';

export default function App() {
  const [sql, setSqlValue] = useState(exampleSql);
  const [dialect, setDialect] = useState('spark');
  const [activeNav, setActiveNav] = useState('workbench');
  const [state, setState] = useState<WorkbenchState>(initialWorkbenchState);
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
    setState((s) => (s.selectedEntity === entityId ? s : { ...s, selectedEntity: entityId }));
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
    setState((s) => applySqlDraftChange(s, value));
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
    setState((s) => buildAnalyzeRunningState(s));
    try {
      const result = await analyzeSql(sql, dialect);
      setState((s) => buildAnalyzeSuccessState(s, result));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Analyze request failed';
      setState((s) => buildAnalyzeFailureState(s, message));
    }
  };

  const onSelectResult = (item: SearchItem) => {
    setState((s) => applySearchSelection(s, item));
  };

  const setSplit = (split: number) => setState((s) => ({ ...s, split }));
  const workspaceStyle = useMemo(() => ({ ['--split' as string]: `${state.split}%` }), [state.split]);
  const isConvertPage = activeNav === 'convert';
  const isDebugPage = activeNav === 'debug';

  return (
    <div className="app" style={workspaceStyle}>
      {isConvertPage ? (
        <ConvertTopBar backendStatus={state.backendStatus} />
      ) : (
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
                setState((s) => ({ ...s, backendMessage: `Formatted by /api/sql/format | ${response.dialect}` }));
              }
            } catch (err) {
              const message = err instanceof Error ? err.message : 'Format request failed';
              setState((s) => ({
                ...s,
                backendMessage: message,
                drawerOpen: s.drawerOpen,
                drawerTab: s.drawerTab,
                backendDiagnostics: [{
                  id: 'format-api-error',
                  code: 'FORMAT_API_ERROR',
                  entityId: 'out:group',
                  severity: 'error',
                  reason: message,
                  impact: 'The UI could not call /api/sql/format.',
                  action: 'Start the backend service or inspect the format endpoint.',
                }],
              }));
            }
          }}
          onLoadExample={() => {
            setSqlValue(exampleSql);
            setState((s) => ({ ...s, pageMode: 'ready', analysisStatus: 'none', trustStatus: 'untrusted' }));
          }}
          onMetadata={() => setMetadataOpen(true)}
          onMore={() => setState((s) => ({ ...s, drawerOpen: !s.drawerOpen, drawerTab: 'more' }))}
        />
      )}
      <div className="body">
        <LeftNav
          active={activeNav}
          onOpen={(tab) => {
            setActiveNav(tab);
            if (tab !== 'workbench' && tab !== 'convert' && tab !== 'debug') {
              setState((s) => ({ ...s, drawerOpen: true, drawerTab: tab }));
            }
          }}
        />
        <main className="app-main">
          {isConvertPage ? (
            <DialectConvertPage />
          ) : isDebugPage ? (
            <DebugPage state={state} dialect={dialect} sql={sql} />
          ) : (
            <>
              <div className="workspace" id="workspace">
                <SqlEditorPanel
                  sql={sql}
                  setSql={setSql}
                  state={state}
                  dialect={dialect}
                  sourceLocations={state.sourceLocations}
                  onEditorMounted={handleEditorMounted}
                  onCursorEntityChange={handleCursorEntityChange}
                />
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
            </>
          )}
        </main>
      </div>
      <MetadataDialog open={metadataOpen} onClose={() => setMetadataOpen(false)} onImported={refreshMetadataStatus} />
    </div>
  );
}
