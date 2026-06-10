import type { BackendAnalysisResult, ConvertSqlResponse, FormatSqlResponse, MetadataImportResult, MetadataListResponse, MetadataPayload } from '../types/lineage';

function normalizeDialect(dialect: string) {
  const value = dialect.trim().toLowerCase();
  if (value === 'sr') return 'starrocks';
  return value || 'spark';
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

export function formatSql(sql: string, dialect: string) {
  return request<FormatSqlResponse>('/api/sql/format', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sql, dialect: normalizeDialect(dialect) }),
  });
}

export function convertSql(sql: string, sourceDialect: string, targetDialect: string) {
  return request<ConvertSqlResponse>('/api/sql/convert', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sql,
      source_dialect: normalizeDialect(sourceDialect),
      target_dialect: normalizeDialect(targetDialect),
      pretty: true,
    }),
  });
}

export function getHealth() {
  return request<{ status: string; service: string; version: string }>('/api/health');
}

export function analyzeSql(sql: string, dialect: string) {
  return request<BackendAnalysisResult>('/api/sql/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sql,
      dialect: normalizeDialect(dialect),
      analysis_level: 'column',
      default_catalog: 'default',
      default_schema: 'default',
      metadata_version: 'latest',
      case_sensitive: false,
      analysis_options: {
        include_graph: true,
        include_semantics: false,
        include_diagnostics: true,
        include_source_location: true,
        include_expression_lineage: false,
      },
    }),
  });
}

export function previewMetadata(payload: MetadataPayload) {
  return request<MetadataImportResult>('/api/metadata/import/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: 'preview', payload }),
  });
}

export function commitMetadata(payload: MetadataPayload) {
  return request<MetadataImportResult>('/api/metadata/import/commit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: 'commit', payload }),
  });
}

export function listMetadataTables() {
  return request<MetadataListResponse>('/api/metadata/tables');
}

export function listMetadataColumns(table = '') {
  const params = table ? `?table=${encodeURIComponent(table)}` : '';
  return request<MetadataListResponse>(`/api/metadata/columns${params}`);
}
