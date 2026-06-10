import { useEffect, useMemo, useRef, useState } from 'react';
import Editor, { DiffEditor, loader } from '@monaco-editor/react';
import { convertSql, formatSql } from '../api/client';
import type { BackendDiagnostic } from '../types/lineage';

loader.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.50.0/min/vs' } });

type Dialect = 'hive' | 'spark' | 'starrocks';
type ConvertStatus = 'idle' | 'running' | 'success' | 'partial' | 'failed';
type DiffMode = 'split' | 'target_only';

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
  const [diffMode, setDiffMode] = useState<DiffMode>('split');
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
  const [splitStart, setSplitStart] = useState({ x: 0, split: 50 });
  const workspaceRef = useRef<HTMLDivElement | null>(null);

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

  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      if (!splitDragging) return;
      const width = workspaceRef.current?.getBoundingClientRect().width || window.innerWidth;
      const next = splitStart.split + ((event.clientX - splitStart.x) / width) * 100;
      setEditSplit(Math.max(30, Math.min(70, next)));
    };
    const onUp = () => setSplitDragging(false);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [splitDragging, splitStart]);

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
          <div className="view-toggle">
            <button className={`view-btn ${diffMode === 'split' ? 'active' : ''}`} onClick={() => setDiffMode('split')}>Compare</button>
            <button className={`view-btn ${diffMode === 'target_only' ? 'active' : ''}`} onClick={() => setDiffMode('target_only')}>Edit Target</button>
          </div>
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
        className="convert-workspace"
        style={{ ['--convert-split' as string]: `${editSplit}%` }}
      >
        {diffMode === 'split' ? (
          <section className="convert-compare-panel">
            <div className="panel-head">
              <div>
                <b>Diff Preview</b>
                <span className="badge">{sourceDialect}</span>
                <span className="badge">{targetDialect}</span>
              </div>
              <button className="btn-primary secondary" onClick={onCopyTarget} disabled={!targetSql.trim()}>Copy Target</button>
            </div>
            <div className="editor-body">
              <DiffEditor
                height="100%"
                language="sql"
                theme="vs"
                original={sourceSql}
                modified={targetSql}
                onMount={(editor) => {
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
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  wordWrap: 'on',
                  automaticLayout: true,
                }}
              />
            </div>
            <div className="editor-foot">
              <span>Compare view</span>
              <span>{sourceSql.split('\n').length} source lines / {targetSql.split('\n').length} target lines</span>
            </div>
          </section>
        ) : (
          <>
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
                  options={{
                    fontSize: 13,
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    wordWrap: 'on',
                    automaticLayout: true,
                  }}
                />
              </div>
              <div className="editor-foot">
                <span>{sourceDialect} source editor</span>
                <span>{sourceSql.split('\n').length} lines</span>
              </div>
            </section>

            <div className="convert-splitter-zone">
              {splitDragging && <div className="overlay show" />}
              <button
                className={`splitter ${splitDragging ? 'dragging' : ''}`}
                aria-label="Resize source and target SQL editors"
                onMouseDown={(event) => {
                  event.preventDefault();
                  setSplitStart({ x: event.clientX, split: editSplit });
                  setSplitDragging(true);
                }}
                onDoubleClick={() => setEditSplit(50)}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowLeft') setEditSplit((value) => Math.max(30, value - 2));
                  if (event.key === 'ArrowRight') setEditSplit((value) => Math.min(70, value + 2));
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
                  <button className="btn-primary secondary" onClick={onCopyTarget} disabled={!targetSql.trim()}>Copy Target</button>
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
                  options={{
                    fontSize: 13,
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    wordWrap: 'on',
                    automaticLayout: true,
                  }}
                />
              </div>
              <div className="editor-foot">
                <span>Edit target view</span>
                <span>{targetSql.split('\n').length} lines</span>
              </div>
            </section>
          </>
        )}
      </div>

      <section className="convert-status-panel">
        <div className="convert-status-bar">
          <span className={`pill ${statusBadgeClass}`}>{convertStatus}</span>
          <span className={`truncate ${conversionRiskSummary ? 'convert-risk-message' : ''}`}>
            {conversionRiskSummary || backendMessage}
          </span>
          <span>{elapsedMs !== null ? `${elapsedMs} ms` : 'No run yet'}</span>
        </div>
        <div className="convert-diagnostics">
          {diagnostics.length === 0 ? (
            <div className="card">No diagnostics. Convert the SQL to inspect compatibility notes and errors.</div>
          ) : (
            diagnostics.map((diagnostic) => (
              <div key={diagnostic.id} className={`card diag ${diagnostic.level}`}>
                <div className="card-title">{diagnostic.code}</div>
                <div>{diagnostic.message}</div>
              </div>
            ))
          )}
        </div>
      </section>
    </section>
  );
}
