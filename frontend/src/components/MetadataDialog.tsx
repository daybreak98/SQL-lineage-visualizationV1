import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { commitMetadata, listMetadataColumns, listMetadataTables, previewMetadata } from '../api/client';
import type { MetadataImportResult, MetadataListResponse, MetadataPayload } from '../types/lineage';
import { cx } from '../utils/cx';

interface Props {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
}

const samplePayload = `{
  "schema_version": "1.0",
  "metadata_version": "ui_v1",
  "case_sensitive": false,
  "default_catalog": "default",
  "default_schema": "default",
  "source_name": "ui",
  "tables": [
    {
      "catalog": "default",
      "schema": "default",
      "name": "dwd_order_di",
      "comment": "订单明细表",
      "columns": [
        { "name": "order_id", "data_type": "string", "comment": "订单ID", "ordinal": 1 },
        { "name": "user_id", "data_type": "string", "comment": "用户ID", "ordinal": 2 },
        { "name": "amount", "data_type": "decimal(18,2)", "comment": "订单金额", "ordinal": 3 }
      ]
    }
  ]
}`;

function parsePayload(text: string): MetadataPayload {
  return JSON.parse(text) as MetadataPayload;
}

interface ColumnDisplay {
  name: string;
  data_type: string;
  comment: string;
}

function extractColumnsFromPayload(payloadText: string): Map<string, ColumnDisplay[]> {
  const map = new Map<string, ColumnDisplay[]>();
  try {
    const parsed = JSON.parse(payloadText);
    const tables: Array<Record<string, unknown>> = parsed?.tables ?? [];
    for (const t of tables) {
      const tableName = String(t.table_name || t.name || '');
      const columns: ColumnDisplay[] = ((t.columns || []) as Array<Record<string, unknown>>).map((c) => ({
        name: String(c.name || ''),
        data_type: String(c.data_type || ''),
        comment: String(c.comment || ''),
      }));
      map.set(tableName, columns);
    }
  } catch {
    // ignore parse errors — payload may not be valid JSON
  }
  return map;
}

interface TableGroup {
  table: string;
  change_type: string;
  columns: ColumnDisplay[];
}

function buildTableGroups(result: MetadataImportResult, payloadText: string): TableGroup[] {
  const payloadColumns = extractColumnsFromPayload(payloadText);
  const tableMap = new Map<string, { change_type: string }>();

  for (const change of result.changes) {
    const t = change.object_ref.table;
    if (!tableMap.has(t)) tableMap.set(t, { change_type: change.change_type });
  }

  return Array.from(tableMap.entries()).map(([table, info]) => ({
    table,
    change_type: info.change_type,
    columns: payloadColumns.get(table) ?? [],
  }));
}

function renderTableGroups(result: MetadataImportResult, payloadText: string): React.ReactNode {
  const groups = buildTableGroups(result, payloadText);
  if (groups.length === 0) return <div className="card">No tables in change list.</div>;

  return groups.map((group) => (
    <div className="table-group-card" key={group.table}>
      <div className="table-group-head">
        <span className={cx('pill', group.change_type === 'added' ? 'trusted' : 'partial')}>{group.change_type}</span>
        <span className="table-group-name">{group.table}</span>
      </div>
      {group.columns.length > 0 ? (
        <div className="table-group-body">
          <div className="table-group-cols">
            {group.columns.map((col, i) => (
              <div className="table-group-col-row" key={`${col.name}-${i}`}>
                <span className="col-name">{col.name}</span>
                <span className="col-comment">{col.comment || '-'}</span>
                <span className="col-type">{col.data_type || '-'}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="table-group-body-empty">No columns in payload</div>
      )}
    </div>
  ));
}

export function MetadataDialog({ open, onClose, onImported }: Props) {
  const [text, setText] = useState(samplePayload);
  const [result, setResult] = useState<MetadataImportResult | null>(null);
  const [tables, setTables] = useState<MetadataListResponse | null>(null);
  const [columns, setColumns] = useState<MetadataListResponse | null>(null);
  const [activeTable, setActiveTable] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const hasBlockingErrors = useMemo(() => result?.diagnostics.some((d) => d.level === 'error') ?? false, [result]);

  useEffect(() => {
    if (!open) return;
    void refreshMetadata();
  }, [open]);

  async function refreshMetadata(table = activeTable) {
    const [nextTables, nextColumns] = await Promise.all([listMetadataTables(), listMetadataColumns(table)]);
    setTables(nextTables);
    setColumns(nextColumns);
  }

  async function runPreview() {
    setLoading(true);
    setError('');
    try {
      const payload = parsePayload(text);
      setResult(await previewMetadata(payload));
      await refreshMetadata();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Preview failed');
    } finally {
      setLoading(false);
    }
  }

  async function runCommit() {
    setLoading(true);
    setError('');
    try {
      const payload = parsePayload(text);
      setResult(await commitMetadata(payload));
      await refreshMetadata();
      onImported();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Commit failed');
    } finally {
      setLoading(false);
    }
  }

  if (!open) return null;

  return (
    <div className="modal-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="metadata-modal" role="dialog" aria-label="Metadata import">
        <header className="metadata-modal-head">
          <div>
            <div className="card-title">Metadata Import</div>
            <div className="modal-sub">Bound to /api/metadata/import, /tables, and /columns</div>
          </div>
          <button className="btn" onClick={onClose}>Close</button>
        </header>

        <div className="metadata-grid">
          <div className="metadata-pane">
            <div className="pane-title">JSON payload</div>
            <textarea className="metadata-textarea" value={text} onChange={(event) => { setText(event.target.value); setResult(null); }} />
            <div className="metadata-actions">
              <button className="btn" disabled={loading || !text.trim()} onClick={runPreview}>Preview</button>
              <button className="btn-primary" disabled={loading || !text.trim() || hasBlockingErrors} onClick={runCommit}>{result?.status === 'committed' ? 'Committed' : 'Commit'}</button>
              <button className="btn" disabled={loading} onClick={() => { setText(samplePayload); setResult(null); }}>Load sample</button>
            </div>
            {error && <div className="card diag error"><div className="card-title">Request failed</div>{error}</div>}
          </div>

            <div className="metadata-pane">
            <div className="pane-title">Preview / commit result</div>
            {loading && <div className="card">Calling backend...</div>}
            {!loading && !result && <div className="card">Run preview to inspect backend validation and change summary.</div>}
            {result && (
              <div className="metadata-result">
                <div className={cx('pill', result.status === 'committed' ? 'trusted' : hasBlockingErrors ? 'failed' : 'partial')}>{result.status} · {result.metadata_version}</div>
                <div className="metadata-table-list">
                  {renderTableGroups(result, text)}
                </div>
                {result.diagnostics.map((diagnostic) => (
                  <div className={cx('card diag', diagnostic.level)} key={diagnostic.diagnostic_id || diagnostic.code}>
                    <div className="card-title">{diagnostic.code}</div>
                    {diagnostic.message}
                    {diagnostic.suggestion && <><br /><b>Suggestion:</b> {diagnostic.suggestion}</>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <footer className="metadata-footer">
          <div className="metadata-pane">
            <div className="pane-title">Imported tables ({tables?.total ?? 0})</div>
            <div className="metadata-list">
              {(tables?.tables || []).map((table) => {
                const name = String(table.table_name || table.name || table.normalized_table_name || '-');
                return <button className="result" key={`${table.catalog}.${table.schema_name}.${name}`} onClick={() => { setActiveTable(name); void refreshMetadata(name); }}><span><span className="result-title">{name}</span><span className="result-sub">{String(table.comment || table.schema_name || '')}</span></span><span className="reason">table</span></button>;
              })}
            </div>
          </div>
          <div className="metadata-pane">
            <div className="pane-title">Columns {activeTable ? `· ${activeTable}` : ''} ({columns?.total ?? 0})</div>
            <div className="metadata-list">
              {(columns?.columns || []).map((column, index) => <div className="result metadata-column" key={`${column.column_name}-${index}`}><span><span className="result-title">{String(column.column_name || '-')}</span><span className="result-sub">{String(column.comment || '')}</span></span><span className="reason">{String(column.data_type || 'unknown')}</span></div>)}
            </div>
          </div>
        </footer>
      </section>
    </div>
  );
}
