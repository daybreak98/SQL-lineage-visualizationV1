import type { analyzeSubfieldSql } from '../api/client';
import { isUnverifiedPhysicalRead } from './unverifiedUnion';

type Request = Parameters<typeof analyzeSubfieldSql>[0];
type JsonRecord = Record<string, unknown>;
type Range = { start: number; end: number };

export type EvidenceOrigin =
  | { kind: 'AD_HOC' }
  | { kind: 'CONSTRUCTED'; context?: string }
  | {
    kind: 'EXCERPT' | 'ORIGINAL';
    manifest_ref?: string;
    archive_sha256?: string;
    member?: string;
    member_ordinal?: number;
    original_size?: number;
    original_sha256?: string;
    byte_range?: Range;
    range_sha256?: string;
    encoding?: 'utf-8';
    context?: string;
  };

export interface EvidenceSnapshot {
  requestId: string;
  capturedAt: string;
  request: Request;
  rawResponse: unknown;
  origin: EvidenceOrigin;
}

const encoder = new TextEncoder();
const record = (value: unknown): value is JsonRecord =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

async function sha256(bytes: Uint8Array) {
  if (!globalThis.crypto?.subtle) throw new Error('当前浏览器环境不支持 SHA-256 证据核验。');
  const hash = await globalThis.crypto.subtle.digest('SHA-256', new Uint8Array(bytes));
  return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('');
}

export const submittedSqlHash = (sql: string) => sha256(encoder.encode(sql));

function range(value: unknown, limit: number): Range | null {
  if (!record(value)) return null;
  const { start, end } = value;
  return typeof start === 'number' && typeof end === 'number' &&
    Number.isSafeInteger(start) && Number.isSafeInteger(end) &&
    0 <= start && start < end && end <= limit ? { start, end } : null;
}

function resolveOrigin(origin: EvidenceOrigin, sqlHash: string) {
  if (origin.kind === 'AD_HOC' || origin.kind === 'CONSTRUCTED') {
    return { origin: { kind: origin.kind, verification: 'NOT_APPLICABLE',
      ...(origin.kind === 'CONSTRUCTED' && origin.context ? { context: origin.context } : {}) } as const, reason: 'NO_ORIGINAL' };
  }
  if (origin.range_sha256 && origin.range_sha256 !== sqlHash) {
    const reason = 'DECLARED_RANGE_HASH_MISMATCH';
    return { origin: { kind: 'AD_HOC', verification: 'NOT_APPLICABLE', reason } as const, reason };
  }
  // The browser has no trusted original-member witness; copy declarations only.
  const { kind, manifest_ref, archive_sha256, member, member_ordinal, original_size,
    original_sha256, byte_range, range_sha256, encoding, context } = origin;
  const reason = 'ORIGINAL_BYTES_NOT_VERIFIED';
  return { origin: { kind, manifest_ref, archive_sha256, member, member_ordinal, original_size,
    original_sha256, byte_range, range_sha256, encoding, context, verification: 'DECLARED', reason } as const, reason };
}

const pointerToken = (key: string) => key.replace(/~/g, '~0').replace(/\//g, '~1');
const evidenceArrays = ['uses', 'mappings', 'unknowns', 'windows', 'row_selections', 'generators', 'union_output_reads'];
const positionalArrays = new Set([...evidenceArrays,
  'keys', 'port_reads', 'protected_outputs', 'unmatched_protected_outputs', 'by_protected_output', 'unresolved']);

function evidenceLocations(response: JsonRecord, sql: string, originalReason: string) {
  const limit = Array.from(sql).length;

  const locate = (fact_ref: string, value: unknown) => {
    const span = range(value, limit);
    const request_span = span && { unit: 'UNICODE_CODE_POINT' as const, ...span };
    const reason = span ? originalReason : value == null ? 'POSITION_NOT_RECORDED' : 'INVALID_REQUEST_SPAN';
    return { fact_ref, request_span, original_span: null, status: span ? 'REQUEST_ONLY' : 'NO_POSITION', reason };
  };

  const locations: ReturnType<typeof locate>[] = [];
  function visit(value: unknown, pointer: string, field: string) {
    if (Array.isArray(value)) {
      value.forEach((entry, index) => visit(entry, `${pointer}/${index}`, field));
    } else if (record(value)) {
      // Keep the raw diagnostic, but do not index it as an evidence location.
      if (isUnverifiedPhysicalRead(value)) return;
      if ('position' in value || positionalArrays.has(field) || field === 'protected_output') {
        locations.push(locate(pointer, value.position));
      }
      for (const [key, child] of Object.entries(value)) {
        if (key === 'position') continue;
        const childPointer = `${pointer}/${pointerToken(key)}`;
        if (key.endsWith('_position')) locations.push(locate(childPointer, child));
        else visit(child, childPointer, key);
      }
    }
  }
  for (const field of [...evidenceArrays, 'review']) visit(response[field], `/${field}`, field);
  return locations;
}

export async function buildEvidenceBundle({ requestId, capturedAt, request, rawResponse, origin }:
EvidenceSnapshot) {
  const submitted = JSON.parse(JSON.stringify(request)) as Request;
  const response: unknown = structuredClone(rawResponse);
  const declared = structuredClone(origin);
  if (!record(response) || !record(response.coverage)) throw new Error('服务响应未提供 SQL 核验信息。');
  const coverage = response.coverage;
  const sqlHash = await submittedSqlHash(submitted.sql);
  if (coverage.sql_sha256 !== sqlHash || coverage.dialect !== submitted.dialect) {
    throw new Error('提交 SQL 或方言与服务响应不匹配，无法导出证据。');
  }
  const original = resolveOrigin(declared, sqlHash);
  return {
    format: 'subfield-evidence/v1' as const,
    request_id: requestId,
    captured_at: capturedAt,
    endpoint: '/api/sql/subfield-lineage',
    request: submitted,
    submitted_sql_sha256: sqlHash,
    origin: original.origin,
    runtime: { dialect: coverage.dialect, ...(typeof coverage.sqlglot === 'string' ? { sqlglot: coverage.sqlglot } : {}) },
    response,
    locations: evidenceLocations(response, submitted.sql, original.reason),
  };
}
