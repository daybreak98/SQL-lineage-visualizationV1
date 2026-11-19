import type { BackendAnalysisResult, ConvertSqlResponse, FormatSqlResponse, MetadataImportResult, MetadataListResponse, MetadataPayload, MetadataUploadResponse } from '../types/lineage';

function normalizeDialect(dialect: string) {
  const value = dialect.trim().toLowerCase();
  if (value === 'sr') return 'starrocks';
  return value || 'spark';
}

function subfieldValidationMessage(status: number, detail: unknown): string | undefined {
  if (status === 413) return '提交内容超过服务请求大小上限。请缩短 SQL，或从本机文件只提交需要分析的片段。';
  if (status !== 422) return;

  if (detail && typeof detail === 'object' && 'code' in detail && detail.code === 'CONFLICTING_SOURCE_SCHEMAS') {
    return '源列清单中的同一来源声明互相冲突。请检查「源列清单」并保留一致的声明后重试。';
  }

  // Do not display msg, input, or raw field/identifier text from a validation response.
  const messages = new Set<string>();
  if (Array.isArray(detail)) for (const issue of detail) {
    if (!issue || !Array.isArray(issue.loc) || issue.loc[0] !== 'body') continue;
    const field = issue.loc[1] === 'SubfieldRequest' ? issue.loc[2] : issue.loc[1];
    if (field === 'sql') {
      if (issue.type === 'string_too_long' || issue.type === 'value_error.any_str.max_length') {
        messages.add('SQL 超过 65,536 个 Unicode 字符的分析上限。请缩短粘贴内容，或从本机文件选择所需片段。');
      } else {
        messages.add('SQL 输入为空或格式无效。请在编辑器中输入 SQL 文本后重试。');
      }
    } else if (field === 'dialect') {
      messages.add('SQL 方言无效。请选择 Spark 或 Hive 后重试。');
    } else if (field === 'source_schemas') {
      messages.add('源列清单格式不正确。请检查「源列清单」中的 JSON 结构。');
    } else if (field === 'protected_outputs') {
      messages.add('输出槽位无效。请重新分析 SQL，再从当前结果选择检查范围。');
    } else if (field === 'candidate_keys') {
      messages.add('待核查的键无效。请检查源表、JSON 列和顶层键名。');
    }
  }
  return [...messages].join(' ') || '服务未接受这次分析输入。请检查 SQL 文本、方言及可选源列清单后重试。';
}

async function request<T>(url: string, init?: RequestInit, validationMessage?: typeof subfieldValidationMessage): Promise<T> {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    if (response.status === 429 && detail === 'SQL service is busy') {
      throw new Error('另一条 SQL 分析正在运行。请等它结束后重试。');
    }
    const message = validationMessage?.(response.status, detail) ?? (typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map((issue) => issue?.msg).filter(Boolean).join('；') || `HTTP ${response.status}`
      : detail?.message || `HTTP ${response.status}`);
    throw new Error(message);
  }
  return payload as T;
}

interface SubfieldAnalysisRequest {
  sql: string;
  dialect: string;
  source_schemas?: Record<string, unknown>;
  protected_outputs?: { statement: number; scope: string; slot: number }[];
  include_two_step_evidence?: boolean;
  candidate_keys?: { source: string; column: string; keys: string[] }[];
}

export function analyzeSubfieldSql(payload: SubfieldAnalysisRequest) {
  return request<unknown>('/api/sql/subfield-lineage', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ ...payload, dialect: normalizeDialect(payload.dialect) }),
  }, subfieldValidationMessage);
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

export function uploadMetadataDb(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return request<MetadataUploadResponse>('/api/metadata/upload-db', {
    method: 'POST',
    body: formData,
  });
}
