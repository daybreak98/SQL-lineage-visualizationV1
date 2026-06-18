import { useEffect, useMemo, useRef, useState } from 'react';
import Editor, { DiffEditor } from '@monaco-editor/react';
import type { editor as MonacoEditor } from 'monaco-editor';
import { convertSql, formatSql } from '../api/client';
import type { BackendDiagnostic } from '../types/lineage';
import {
  bindModelDialect,
  configureSqlMonacoLoader,
  registerSqlLanguageProviders,
  unbindModelDialect,
} from '../components/SqlEditor/providers';

configureSqlMonacoLoader();

type Dialect = 'hive' | 'spark' | 'starrocks';
type ConvertStatus = 'idle' | 'running' | 'success' | 'partial' | 'failed';

const exampleSqlByDialect: Record<Dialect, string> = {
  hive: [
    "insert overwrite table app.order_metric partition(dt='20260101')",
    'select',
    '  user_id,',
    '  count(distinct order_id) as order_cnt,',
    '  sum(amount) as gmv',
    'from dwd_order_di',
    'group by user_id',
  ].join('\n'),
  spark: [
    'with base as (',
    '  select user_id, amount, order_id from dwd_order_di',
    ')',
    'select',
    '  user_id,',
    '  count(distinct order_id) as order_cnt,',
    '  sum(amount) as gmv',
    'from base',
    'group by 1',
  ].join('\n'),
  starrocks: [
    'select',
    '  user_id,',
    '  sum(amount) as gmv',
    'from dwd_order_di',
    'where dt = 20260101',
    'group by user_id',
  ].join('\n'),
};

function normalizeDiagnostics(diagnostics: BackendDiagnostic[]) {
  return diagnostics.map((diagnostic, index) => ({
    id: `${diagnostic.code}-${index}`,
    code: diagnostic.code,
    level: diagnostic.level,
    message: diagnostic.message,
    location: diagnostic.location,
    extra: diagnostic.extra,
  }));
}

export function DialectConvertPage() {
  const [sourceDialect, setSourceDialect] = useState<Dialect>('hive');
  const [targetDialect, setTargetDialect] = useState<Dialect>('spark');
  const [sourceSql, setSourceSql] = useState(exampleSqlByDialect.hive);
  const [targetSql, setTargetSql] = useState('');
  const [convertStatus, setConvertStatus] = useState<ConvertStatus>('idle');
  const [showDiff, setShowDiff] = useState(false);
  const [diagnostics, setDiagnostics] = useState<Array<{
    id: string;
    code: string;
    level: string;
    message: string;
    location?: Record<string, unknown> | null;
    extra?: Record<string, unknown>;
  }>>([]);
  const [backendMessage, setBackendMessage] = useState('Ready to convert SQL between Hive, Spark, and StarRocks.');
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [isTargetDirty, setIsTargetDirty] = useState(false);
  const [editSplit, setEditSplit] = useState(50);
  const [splitDragging, setSplitDragging] = useState(false);
  const workspaceRef = useRef<HTMLDivElement | null>(null);
  const splitDragRef = useRef({ pointerId: -1, x: 0, split: 50 });
  const splitDraggingRef = useRef(false);
  const sourceDialectRef = useRef(sourceDialect);
  const targetDialectRef = useRef(targetDialect);
  sourceDialectRef.current = sourceDialect;
  targetDialectRef.current = targetDialect;

  const clampEditSplit = (value: number) => Math.max(30, Math.min(70, value));

  const updateEditSplitFromPointer = (clientX: number) => {
    const bounds = workspaceRef.current?.getBoundingClientRect();
    const width = Math.max(bounds?.width ?? window.innerWidth, 1);
    const next = splitDragRef.current.split + ((clientX - splitDragRef.current.x) / width) * 100;
    setEditSplit(clampEditSplit(next));
  };

  const stopSplitDrag = () => {
    splitDragRef.current.pointerId = -1;
    splitDraggingRef.current = false;
    setSplitDragging(false);
  };

  const statusBadgeClass = useMemo(() => {
    if (convertStatus === 'success') return 'trusted';
    if (convertStatus === 'partial') return 'partial';
    if (convertStatus === 'failed') return 'failed';
    if (convertStatus === 'running') return 'running';
    return '';
  }, [convertStatus]);

  const conversionRiskSummary = useMemo(() => {
    const sourceRiskDiagnostics = diagnostics.filter((diagnostic) => diagnostic.code === 'FUNCTION_CONVERSION_UNCERTAIN');
    const riskDiagnostics = sourceRiskDiagnostics.length > 0
      ? sourceRiskDiagnostics
      : diagnostics.filter((diagnostic) => diagnostic.code === 'FUNCTION_PASSTHROUGH');
    if (riskDiagnostics.length === 0) return '';
    const items = riskDiagnostics.map((diagnostic) => {
      const line = typeof diagnostic.location?.line === 'number' ? `Line ${diagnostic.location.line}` : 'Line ?';
      const functionName = typeof diagnostic.extra?.function === 'string' ? diagnostic.extra.function : 'unknown function';
      return `${line}: ${functionName}`;
    });
    return `Unsupported or uncertain function conversion: ${items.join('; ')}`;
  }, [diagnostics]);

  const showDiagnosticsPanel = diagnostics.length > 0;
  const statusMessage = conversionRiskSummary
    || (showDiagnosticsPanel
      ? backendMessage
      : `${backendMessage} No diagnostics. Convert the SQL to inspect compatibility notes and errors.`);

  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      if (!splitDraggingRef.current) return;
      if (splitDragRef.current.pointerId !== -1 && event.pointerId !== splitDragRef.current.pointerId) return;
      updateEditSplitFromPointer(event.clientX);
    };

    const onUp = (event: PointerEvent) => {
      if (!splitDraggingRef.current) return;
      if (splitDragRef.current.pointerId !== -1 && event.pointerId !== splitDragRef.current.pointerId) return;
      stopSplitDrag();
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
    };
  }, []);

  const onConvert = async () => {
    if (!sourceSql.trim()) return;
    setConvertStatus('running');
    setBackendMessage(`Converting ${sourceDialect} -> ${targetDialect}...`);
    try {
      const response = await convertSql(sourceSql, sourceDialect, targetDialect);
      setTargetSql(response.converted_sql || '');
      setConvertStatus(response.status);
      setDiagnostics(normalizeDiagnostics(response.diagnostics));
      setElapsedMs(response.elapsed_ms);
      setIsTargetDirty(false);
      setBackendMessage(`${response.source_dialect} -> ${response.target_dialect} conversion completed.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Convert request failed';
      setConvertStatus('failed');
      setDiagnostics([{ id: 'convert-error', code: 'CONVERT_API_ERROR', level: 'error', message }]);
      setElapsedMs(null);
      setBackendMessage(message);
    }
  };

  const onFormatSource = async () => {
    if (!sourceSql.trim()) return;
    try {
      const response = await formatSql(sourceSql, sourceDialect);
      if (response.formatted_sql) {
        setSourceSql(response.formatted_sql);
        setBackendMessage(`Formatted source SQL as ${response.dialect}.`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Format source failed';
      setBackendMessage(message);
    }
  };

  const onFormatTarget = async () => {
    if (!targetSql.trim()) return;
    try {
      const response = await formatSql(targetSql, targetDialect);
      if (response.formatted_sql) {
        setTargetSql(response.formatted_sql);
        setIsTargetDirty(true);
        setBackendMessage(`Formatted target SQL as ${response.dialect}.`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Format target failed';
      setBackendMessage(message);
    }
  };

  const onSwap = () => {
    setSourceDialect(targetDialect);
    setTargetDialect(sourceDialect);
    setSourceSql(targetSql || exampleSqlByDialect[targetDialect]);
    setTargetSql(sourceSql);
    setIsTargetDirty(false);
    setDiagnostics([]);
    setConvertStatus('idle');
    setElapsedMs(null);
    setBackendMessage('Swapped source and target dialects.');
  };

  const onCopyTarget = async () => {
    if (!targetSql) return;
    try {
      await navigator.clipboard.writeText(targetSql);
      setBackendMessage('Target SQL copied to clipboard.');
    } catch {
      setBackendMessage('Clipboard copy is not available in this environment.');
    }
  };

  const onLoadExample = () => {
    setSourceSql(exampleSqlByDialect[sourceDialect]);
    setTargetSql('');
    setDiagnostics([]);
    setConvertStatus('idle');
    setElapsedMs(null);
    setIsTargetDirty(false);
    setBackendMessage(`Loaded ${sourceDialect} example SQL.`);
  };

  const onClear = () => {
    setSourceSql('');
    setTargetSql('');
    setDiagnostics([]);
    setConvertStatus('idle');
    setElapsedMs(null);
    setIsTargetDirty(false);
    setBackendMessage('Cleared both editors.');
  };

  const editorOptions = {
    fontSize: 13,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    wordWrap: 'on' as const,
    automaticLayout: true,
    wordBasedSuggestions: 'off' as const,
    suggest: { showKeywords: true, showSnippets: false },
  };

  const bindStandaloneEditor = (editor: MonacoEditor.IStandaloneCodeEditor, monaco: any, getDialect: () => string) => {
    registerSqlLanguageProviders(monaco);
    const model = editor.getModel();
    bindModelDialect(model, getDialect);
    editor.onDidDispose(() => unbindModelDialect(model));
  };

  const bindDiffEditors = (editor: MonacoEditor.IStandaloneDiffEditor, monaco: any) => {
    registerSqlLanguageProviders(monaco);
    const originalModel = editor.getOriginalEditor().getModel();
    const modifiedModel = editor.getModifiedEditor().getModel();
    bindModelDialect(originalModel, () => sourceDialectRef.current);
    bindModelDialect(modifiedModel, () => targetDialectRef.current);
    editor.onDidDispose(() => {
      unbindModelDialect(originalModel);
      unbindModelDialect(modifiedModel);
    });
  };

  return (
    <section className="convert-page">
      <div className="convert-toolbar">
        <div className="convert-group">
          <label className="convert-label">
            <span>Source</span>
            <select className="select" value={sourceDialect} onChange={(event) => setSourceDialect(event.target.value as Dialect)}>
              <option value="hive">Hive</option>
              <option value="spark">Spark</option>
              <option value="starrocks">StarRocks</option>
            </select>
          </label>
          <label className="convert-label">
            <span>Target</span>
            <select className="select" value={targetDialect} onChange={(event) => setTargetDialect(event.target.value as Dialect)}>
              <option value="hive">Hive</option>
              <option value="spark">Spark</option>
              <option value="starrocks">StarRocks</option>
            </select>
          </label>
          <button className="btn" onClick={onSwap}>Swap</button>
        </div>
        <div className="convert-group">
          <button className={`tool-btn ${showDiff ? 'active' : ''}`} onClick={() => setShowDiff((value) => !value)}>
            {showDiff ? 'Hide Diff' : 'Show Diff'}
          </button>
          <button className="tool-btn" onClick={onLoadExample}>Example</button>
          <button className="tool-btn" onClick={onFormatSource} disabled={!sourceSql.trim()}>Format Source</button>
          <button className="tool-btn" onClick={onClear}>Clear</button>
          <button className="btn-primary" onClick={onConvert} disabled={!sourceSql.trim() || convertStatus === 'running'}>
            {convertStatus === 'running' ? 'Converting...' : 'Convert'}
          </button>
        </div>
      </div>

      <div
        ref={workspaceRef}
        className={`convert-workspace ${showDiff ? 'diff-active' : ''}`}
        style={{ ['--convert-split' as string]: `${editSplit}%`, position: 'relative' }}
      >
        <section className="editor convert-source">
          <div className="panel-head">
            <div><b>Source SQL</b><span className="badge">{sourceDialect}</span></div>
            <button className="tool-btn" onClick={onFormatSource}>Format</button>
          </div>
          <div className="editor-body">
            <Editor
              height="100%"
              language="sql"
              theme="vs"
              value={sourceSql}
              onChange={(value) => setSourceSql(value || '')}
              onMount={(editor, monaco) => bindStandaloneEditor(editor, monaco, () => sourceDialectRef.current)}
              options={editorOptions}
            />
          </div>
          <div className="editor-foot">
            <span>{sourceDialect} source editor</span>
            <span>{sourceSql.split('\n').length} lines</span>
          </div>
        </section>

        <div className={`convert-splitter-zone ${showDiff ? 'hidden' : ''}`}>
          {splitDragging && <div className="overlay show" />}
          <button
            type="button"
            className={`splitter ${splitDragging ? 'dragging' : ''}`}
            aria-label="Resize source and target SQL editors"
            onPointerDown={(event) => {
              if (event.button !== 0) return;
              event.preventDefault();
              if (typeof event.currentTarget.setPointerCapture === 'function') {
                event.currentTarget.setPointerCapture(event.pointerId);
              }
              splitDragRef.current = { pointerId: event.pointerId, x: event.clientX, split: editSplit };
              splitDraggingRef.current = true;
              setSplitDragging(true);
            }}
            onPointerUp={(event) => {
              if (typeof event.currentTarget.hasPointerCapture === 'function'
                && typeof event.currentTarget.releasePointerCapture === 'function'
                && event.currentTarget.hasPointerCapture(event.pointerId)) {
                event.currentTarget.releasePointerCapture(event.pointerId);
              }
              stopSplitDrag();
            }}
            onPointerCancel={(event) => {
              if (typeof event.currentTarget.hasPointerCapture === 'function'
                && typeof event.currentTarget.releasePointerCapture === 'function'
                && event.currentTarget.hasPointerCapture(event.pointerId)) {
                event.currentTarget.releasePointerCapture(event.pointerId);
              }
              stopSplitDrag();
            }}
            onLostPointerCapture={stopSplitDrag}
            onDoubleClick={() => setEditSplit(50)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowLeft') setEditSplit((value) => clampEditSplit(value - 2));
              if (event.key === 'ArrowRight') setEditSplit((value) => clampEditSplit(value + 2));
            }}
          >
            <span className="splitter-line" />
          </button>
          <div className={`split-tooltip ${splitDragging ? 'show' : ''}`}>
            Source {Math.round(editSplit)}% / Target {Math.round(100 - editSplit)}%
          </div>
        </div>

        <section className="convert-target-panel">
          <div className="panel-head">
            <div>
              <b>Target SQL</b>
              <span className="badge">{targetDialect}</span>
              {isTargetDirty && <span className="badge">modified</span>}
            </div>
            <div className="convert-head-actions">
              <button
                className={`btn-copy ${!isTargetDirty && targetSql.trim() ? 'btn-copy-clean' : ''}`}
                onClick={onCopyTarget}
                disabled={!targetSql.trim()}
              >
                Copy Target
              </button>
              <button className="tool-btn" onClick={onFormatTarget} disabled={!targetSql.trim()}>Format</button>
            </div>
          </div>
          <div className="editor-body">
            <Editor
              height="100%"
              language="sql"
              theme="vs"
              value={targetSql}
              onChange={(value) => {
                setTargetSql(value || '');
                setIsTargetDirty(true);
              }}
              onMount={(editor, monaco) => bindStandaloneEditor(editor, monaco, () => targetDialectRef.current)}
              options={editorOptions}
            />
          </div>
          <div className="editor-foot">
            <span>{targetDialect} target editor</span>
            <span>{targetSql.split('\n').length} lines</span>
          </div>
        </section>

        {showDiff && (
          <div className="diff-overlay">
            <div className="diff-overlay-head">
              <div>
                <b>Diff Preview</b>
                <span className="badge">{sourceDialect}</span>
                <span className="badge">{targetDialect}</span>
              </div>
              <button className="btn" onClick={() => setShowDiff(false)}>Close Diff</button>
            </div>
            <div className="diff-overlay-body">
              <DiffEditor
                height="100%"
                language="sql"
                theme="vs"
                original={sourceSql}
                modified={targetSql}
                onMount={(editor, monaco) => {
                  bindDiffEditors(editor, monaco);
                  const modifiedEditor = editor.getModifiedEditor();
                  modifiedEditor.onDidChangeModelContent(() => {
                    setTargetSql(modifiedEditor.getValue());
                    setIsTargetDirty(true);
                  });
                }}
                options={{
                  readOnly: false,
                  originalEditable: false,
                  renderSideBySide: true,
                  ...editorOptions,
                }}
              />
            </div>
          </div>
        )}
      </div>

      <section className={`convert-status-panel ${showDiagnosticsPanel ? '' : 'compact'}`}>
        <div className="convert-status-bar">
          <span className={`pill ${statusBadgeClass}`}>{convertStatus}</span>
          <span className={`truncate ${conversionRiskSummary ? 'convert-risk-message' : ''}`}>
            {statusMessage}
          </span>
          <span>{elapsedMs !== null ? `${elapsedMs} ms` : 'No run yet'}</span>
        </div>
        {showDiagnosticsPanel && (
          <div className="convert-diagnostics">
            {diagnostics.map((diagnostic) => (
              <div key={diagnostic.id} className={`card diag ${diagnostic.level}`}>
                <div className="card-title">{diagnostic.code}</div>
                <div>{diagnostic.message}</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}
