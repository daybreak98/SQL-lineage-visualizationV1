import { useMemo, useState } from 'react';
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
  }));
}

export function DialectConvertPage() {
  const [sourceDialect, setSourceDialect] = useState<Dialect>('hive');
  const [targetDialect, setTargetDialect] = useState<Dialect>('spark');
  const [sourceSql, setSourceSql] = useState(exampleSqlByDialect.hive);
  const [targetSql, setTargetSql] = useState('');
  const [convertStatus, setConvertStatus] = useState<ConvertStatus>('idle');
  const [diffMode, setDiffMode] = useState<DiffMode>('split');
  const [diagnostics, setDiagnostics] = useState<Array<{ id: string; code: string; level: string; message: string }>>([]);
  const [backendMessage, setBackendMessage] = useState('Ready to convert SQL between Hive, Spark, and StarRocks.');
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [isTargetDirty, setIsTargetDirty] = useState(false);

  const statusBadgeClass = useMemo(() => {
    if (convertStatus === 'success') return 'trusted';
    if (convertStatus === 'partial') return 'partial';
    if (convertStatus === 'failed') return 'failed';
    if (convertStatus === 'running') return 'running';
    return '';
  }, [convertStatus]);

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
            <button className={`view-btn ${diffMode === 'split' ? 'active' : ''}`} onClick={() => setDiffMode('split')}>Split Diff</button>
            <button className={`view-btn ${diffMode === 'target_only' ? 'active' : ''}`} onClick={() => setDiffMode('target_only')}>Target Only</button>
          </div>
          <button className="btn" onClick={onLoadExample}>Load Example</button>
          <button className="btn" onClick={onClear}>Clear</button>
          <button className="btn-primary" onClick={onConvert} disabled={!sourceSql.trim() || convertStatus === 'running'}>
            {convertStatus === 'running' ? 'Converting...' : 'Convert'}
          </button>
        </div>
      </div>

      <div className="convert-workspace">
        <section className="editor convert-source">
          <div className="panel-head">
            <div><b>Source SQL</b><span className="badge">{sourceDialect}</span></div>
            <button className="btn" onClick={onFormatSource}>Format Source</button>
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

        <section className="convert-target-panel">
          <div className="panel-head">
            <div>
              <b>Target SQL</b>
              <span className="badge">{targetDialect}</span>
              {isTargetDirty && <span className="badge">modified</span>}
            </div>
            <div className="convert-head-actions">
              <button className="btn" onClick={onFormatTarget} disabled={!targetSql.trim()}>Format Target</button>
              <button className="btn" onClick={onCopyTarget} disabled={!targetSql.trim()}>Copy Target</button>
            </div>
          </div>
          <div className="editor-body">
            {diffMode === 'split' ? (
              <DiffEditor
                height="100%"
                language="sql"
                theme="vs"
                original={sourceSql}
                modified={targetSql}
                options={{
                  readOnly: true,
                  renderSideBySide: true,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  wordWrap: 'on',
                  automaticLayout: true,
                }}
              />
            ) : (
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
            )}
          </div>
          <div className="editor-foot">
            <span>{diffMode === 'split' ? 'Diff view' : 'Editable target view'}</span>
            <span>{targetSql.split('\n').length} lines</span>
          </div>
        </section>
      </div>

      <section className="convert-status-panel">
        <div className="convert-status-bar">
          <span className={`pill ${statusBadgeClass}`}>{convertStatus}</span>
          <span className="truncate">{backendMessage}</span>
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
