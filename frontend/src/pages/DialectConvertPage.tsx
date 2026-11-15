import { useMemo, useRef, useState } from 'react';
import { DiffEditor } from '@monaco-editor/react';
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

function editorTextMatches(left: string, right: string) {
  return left.replace(/\r\n?/g, '\n') === right.replace(/\r\n?/g, '\n');
}

export function DialectConvertPage() {
  const [sourceDialect, setSourceDialect] = useState<Dialect>('spark');
  const [targetDialect, setTargetDialect] = useState<Dialect>('starrocks');
  const [sourceSql, setSourceSql] = useState(exampleSqlByDialect.spark);
  const [targetSql, setTargetSql] = useState('');
  const [convertStatus, setConvertStatus] = useState<ConvertStatus>('idle');
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
  const [conversionFresh, setConversionFresh] = useState(false);
  const sourceSqlRef = useRef(sourceSql);
  const targetSqlRef = useRef(targetSql);
  const sourceDialectRef = useRef(sourceDialect);
  const targetDialectRef = useRef(targetDialect);
  sourceDialectRef.current = sourceDialect;
  targetDialectRef.current = targetDialect;

  const updateSourceSql = (value: string, markStale = true) => {
    sourceSqlRef.current = value;
    setSourceSql(value);
    if (markStale) setConversionFresh(false);
  };

  const updateTargetSql = (value: string, markStale = true) => {
    targetSqlRef.current = value;
    setTargetSql(value);
    if (markStale) setConversionFresh(false);
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

  const onConvert = async () => {
    if (!sourceSql.trim()) return;
    setConvertStatus('running');
    setBackendMessage(`Converting ${sourceDialect} -> ${targetDialect}...`);
    try {
      const response = await convertSql(sourceSql, sourceDialect, targetDialect);
      updateTargetSql(response.converted_sql || '', false);
      setConvertStatus(response.status);
      setDiagnostics(normalizeDiagnostics(response.diagnostics));
      setElapsedMs(response.elapsed_ms);
      setConversionFresh(Boolean(response.converted_sql?.trim()));
      setBackendMessage(`${response.source_dialect} -> ${response.target_dialect} conversion completed.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Convert request failed';
      setConvertStatus('failed');
      setDiagnostics([{ id: 'convert-error', code: 'CONVERT_API_ERROR', level: 'error', message }]);
      setElapsedMs(null);
      setConversionFresh(false);
      setBackendMessage(message);
    }
  };

  const onFormatSource = async () => {
    if (!sourceSql.trim()) return;
    try {
      const response = await formatSql(sourceSql, sourceDialect);
      if (response.formatted_sql) {
        updateSourceSql(response.formatted_sql);
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
        updateTargetSql(response.formatted_sql);
        setBackendMessage(`Formatted target SQL as ${response.dialect}.`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Format target failed';
      setBackendMessage(message);
    }
  };

  const onSwap = () => {
    const nextSourceSql = targetSql || exampleSqlByDialect[targetDialect];
    const nextTargetSql = sourceSql;
    setSourceDialect(targetDialect);
    setTargetDialect(sourceDialect);
    updateSourceSql(nextSourceSql);
    updateTargetSql(nextTargetSql);
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
    updateSourceSql(exampleSqlByDialect[sourceDialect]);
    updateTargetSql('');
    setDiagnostics([]);
    setConvertStatus('idle');
    setElapsedMs(null);
    setBackendMessage(`Loaded ${sourceDialect} example SQL.`);
  };

  const onClear = () => {
    updateSourceSql('');
    updateTargetSql('');
    setDiagnostics([]);
    setConvertStatus('idle');
    setElapsedMs(null);
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

  const bindDiffEditors = (editor: MonacoEditor.IStandaloneDiffEditor, monaco: any) => {
    registerSqlLanguageProviders(monaco);
    const originalModel = editor.getOriginalEditor().getModel();
    const modifiedModel = editor.getModifiedEditor().getModel();
    bindModelDialect(originalModel, () => sourceDialectRef.current);
    bindModelDialect(modifiedModel, () => targetDialectRef.current);
    const originalEditor = editor.getOriginalEditor();
    const modifiedEditor = editor.getModifiedEditor();
    const originalChange = originalEditor.onDidChangeModelContent(() => {
      const value = originalEditor.getValue();
      if (editorTextMatches(value, sourceSqlRef.current)) return;
      updateSourceSql(value);
    });
    const modifiedChange = modifiedEditor.onDidChangeModelContent(() => {
      const value = modifiedEditor.getValue();
      if (editorTextMatches(value, targetSqlRef.current)) return;
      updateTargetSql(value);
    });
    editor.onDidDispose(() => {
      originalChange.dispose();
      modifiedChange.dispose();
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
            <select className="select" value={sourceDialect} onChange={(event) => {
              setSourceDialect(event.target.value as Dialect);
              setConversionFresh(false);
            }}>
              <option value="hive">Hive</option>
              <option value="spark">Spark</option>
              <option value="starrocks">StarRocks</option>
            </select>
          </label>
          <label className="convert-label">
            <span>Target</span>
            <select className="select" value={targetDialect} onChange={(event) => {
              setTargetDialect(event.target.value as Dialect);
              setConversionFresh(false);
            }}>
              <option value="hive">Hive</option>
              <option value="spark">Spark</option>
              <option value="starrocks">StarRocks</option>
            </select>
          </label>
          <button className="btn" onClick={onSwap}>Swap</button>
        </div>
        <div className="convert-group">
          <button className="tool-btn" onClick={onLoadExample}>Example</button>
          <button className="tool-btn" onClick={onClear}>Clear</button>
          <button className="btn-primary" onClick={onConvert} disabled={!sourceSql.trim() || convertStatus === 'running'}>
            {convertStatus === 'running' ? 'Converting...' : 'Convert'}
          </button>
        </div>
      </div>

      <div className="convert-workspace">
        <section className="convert-compare-panel">
          <div className="convert-diff-head">
            <div className="convert-diff-head-side convert-diff-head-source">
              <div>
                <b>Source SQL</b>
                <span className="badge">{sourceDialect}</span>
              </div>
              <button className="tool-btn" onClick={onFormatSource} disabled={!sourceSql.trim()}>Format</button>
            </div>
            <div className="convert-diff-head-side convert-diff-head-target">
              <div>
                <b>Target SQL</b>
                <span className="badge">{targetDialect}</span>
              </div>
              <div className="convert-head-actions">
              <button
                className={`btn-copy ${conversionFresh ? 'btn-copy-ready' : ''}`}
                onClick={onCopyTarget}
                disabled={!targetSql.trim()}
              >
                Copy Target
              </button>
              <button className="tool-btn" onClick={onFormatTarget} disabled={!targetSql.trim()}>Format</button>
              </div>
            </div>
          </div>
          <div className="editor-body">
            <DiffEditor
              height="100%"
              language="sql"
              theme="vs"
              original={sourceSql}
              modified={targetSql}
              onMount={bindDiffEditors}
              options={{
                readOnly: false,
                originalEditable: true,
                renderSideBySide: true,
                ...editorOptions,
              }}
            />
          </div>
          <div className="convert-diff-foot">
            <span>{sourceSql.split('\n').length} source lines</span>
            <span>{targetSql.split('\n').length} target lines</span>
          </div>
        </section>
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
