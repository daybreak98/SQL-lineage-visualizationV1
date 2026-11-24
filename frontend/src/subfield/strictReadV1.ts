import { analyzeSubfieldSql } from '../api/client';
import type { Position, RecordRow } from './contract';
import type { createSQLPositionIndex } from './sqlPositionIndex';
import type { StrictReadLoader, StrictReadPoint, StrictReadResponse } from './StrictReadPreview';

type Index = ReturnType<typeof createSQLPositionIndex>;
type Json = Record<string, unknown>;
type Token = { kind: 'key'; value: string } | { kind: 'index'; value: number };
const record = (value: unknown): Json => value && typeof value === 'object' && !Array.isArray(value) ? value as Json : {};
const text = (value: unknown): value is string => typeof value === 'string' && value.length > 0;
const positiveInteger = (value: unknown) => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
const sameSpan = (a: Position | null, b: Position) => a?.start === b.start && a.end === b.end;
const contains = (a: Position, b: Position) => a.start <= b.start && b.end <= a.end;
function span(value: unknown, index: Index): Position | null {
  const { start, end } = record(value);
  return typeof start === 'number' && typeof end === 'number' && index.valid({ start, end }) ? { start, end } : null;
}
function tokens(value: unknown): Token[] | null {
  if (!Array.isArray(value) || !value.length || value.length > 32) return null;
  const list: Token[] = [];
  for (const raw of value) {
    const { kind, value } = record(raw);
    if (kind === 'key' && typeof value === 'string') list.push({ kind, value });
    else if (kind === 'index' && typeof value === 'number' && Number.isSafeInteger(value) && value >= 0) list.push({ kind, value });
    else return null;
  }
  return list;
}

export function strictReadPoint(row: RecordRow, index: Index): StrictReadPoint | null {
  const use = row.clause === 'SELECT' && row.role === 'VALUE' ? 'SELECT'
    : row.clause === 'WHERE' && row.role === 'CONDITION' ? 'WHERE'
    : row.clause === 'JOIN' && (row.role === 'RELATIONAL' || row.role === 'CONDITION') ? 'ON' : null;
  if (!use || row.kind !== 'EXTRACT' || typeof row.statement !== 'number' || !positiveInteger(row.statement) || !text(row.path) ||
      !index.valid(row.position) || index.excerpt(row.position)?.match.toLowerCase() !== 'get_json_object') return null;
  const pathTokens = tokens(row.path_tokens);
  if (!pathTokens) return null;
  return { statement: row.statement, call_position: row.position, path: row.path, use, pathTokens };
}

function reject(): never { throw new Error('Strict read response did not match the current selector.'); }

type ProvisionalEvidence = NonNullable<StrictReadResponse['strict_read_evidence']>;
const reasons: Record<string, Extract<ProvisionalEvidence, { status: 'UNVERIFIED' }>['reason']> = {
  MIXED_REQUEST: 'MIXED_REQUEST', INVALID_SELECTOR: 'INVALID_SELECTOR', SQL_HASH_MISMATCH: 'SQL_HASH_MISMATCH',
  DIALECT_UNSUPPORTED: 'DIALECT_UNSUPPORTED', EXTERNAL_SCHEMA_UNSUPPORTED: 'EXTERNAL_SCHEMA_UNSUPPORTED',
  STATEMENT_UNSUPPORTED: 'STATEMENT_UNSUPPORTED', SQL_BUDGET_EXCEEDED: 'BUDGET_EXCEEDED',
  SITE_NOT_MATCHED: 'SITE_NOT_MATCHED', SITE_NOT_UNIQUE: 'SITE_NOT_UNIQUE', SITE_UNSUPPORTED: 'UNSUPPORTED_CHAIN',
  SITE_NOT_VISIBLE: 'INPUT_NOT_VISIBLE', SOURCE_CHAIN_UNVERIFIED: 'BINDING_UNVERIFIED',
  BUDGET_EXCEEDED: 'BUDGET_EXCEEDED', OBSERVER_UNAVAILABLE: 'OBSERVATION_FAILED',
};

export function strictReadV1Loader(point: StrictReadPoint, index: Index): StrictReadLoader {
  return async request => {
    const { strict_read_site: selector } = request;
    const raw = record(await analyzeSubfieldSql({ ...request, mode: 'analyze' }));
    if (raw.strict_read_evidence === undefined) return {};
    const block = record(raw.strict_read_evidence), site = record(block.site);
    if (block.version !== 'strict-read.v1' || block.dialect !== request.dialect || block.sql_sha256 !== selector.sql_sha256 ||
        (block.site !== null && (site.statement !== selector.statement ||
          !sameSpan(span(site.call_position, index), selector.call_position)))) reject();
    const identity = { ...selector, dialect: request.dialect, version: 'preview-v1' as const };
    const base = { identity, use: point.use, path: point.path };
    if (block.status === 'UNVERIFIED') {
      if ('witness' in block || !text(block.reason) || !Object.hasOwn(reasons, block.reason)) reject();
      // A null site supplies no trusted anchor. A non-null site may be shown as a diagnostic, not a local binding proof.
      return { strict_read_evidence: { ...base, status: 'UNVERIFIED', reason: reasons[block.reason],
        ...(block.site === null ? {} : { diagnostic_position: selector.call_position }) } };
    }
    if (block.status !== 'WITNESSED' || block.site === null || 'reason' in block) reject();
    const w = record(block.witness);
    const call = span(w.call_span, index), path = span(w.path_literal_span, index);
    const suppliedTokens = tokens(w.path_tokens);
    if (!text(w.snapshot_id) || !text(w.rules_version) || !text(w.scope) ||
        w.clause !== point.use || w.role !== (point.use === 'SELECT' ? 'VALUE' : 'CONDITION') ||
        !call || call.start !== selector.call_position.start || !contains(call, selector.call_position) ||
        !path || path.start < selector.call_position.end || !contains(call, path) || !suppliedTokens ||
        JSON.stringify(suppliedTokens) !== JSON.stringify(point.pathTokens) || !Array.isArray(w.hops) ||
        !w.hops.length || w.hops.length > 32) reject();

    const hops = w.hops.map((entry, i) => {
      const hop = record(entry), relation = record(hop.relation);
      const column = span(hop.column_span, index), qualifier = span(hop.qualifier_span, index);
      const declaration = span(relation.decl_span, index);
      if (!text(hop.scope) || !text(hop.column) || !text(relation.name) || !text(relation.source) ||
          relation.scope !== hop.scope || !column || !qualifier || qualifier.end > column.start || !declaration ||
          !Array.isArray(relation.name_spans) || !relation.name_spans.length ||
          relation.name_spans.some(site => !span(site, index))) reject();
      const reference = { start: qualifier.start, end: column.end };
      if (i === 0 && (hop.scope !== w.scope || !contains(call, reference) || reference.end > path.start)) reject();
      if (hop.visibility !== null) {
        const vis = record(hop.visibility);
        if (!positiveInteger(vis.stage) || !span(vis.on_span, index) || !Array.isArray(vis.input_prefix) ||
            !vis.input_prefix.length || vis.input_prefix.some(site => !span(site, index))) reject();
      } else if (i === 0 && point.use === 'ON') reject();
      return { hop, relation, column, declaration, reference };
    });

    const terminal = record(w.terminal), last = hops[hops.length - 1];
    if (terminal.scope !== last.hop.scope || terminal.column !== last.hop.column || terminal.source !== last.relation.source ||
        !sameSpan(span(terminal.decl_span, index), last.declaration) ||
        !sameSpan(span(terminal.column_span, index), last.column) || last.hop.producer !== null) reject();
    const steps: Extract<ProvisionalEvidence, { status: 'WITNESSED' }>['steps'] = [];
    for (const [i, hop] of hops.entries()) {
      const next = hops[i + 1];
      const producer = record(hop.hop.producer);
      if (next && (producer.statement !== selector.statement || producer.scope !== next.hop.scope || !positiveInteger(producer.slot))) reject();
      steps.push({
        reference: `${hop.relation.name}.${hop.hop.column}`,
        from: next ? `${hop.relation.source}.${hop.hop.column}` : `${terminal.source}.${terminal.column}`,
        reference_position: hop.reference,
        producer_position: next ? next.column : last.column,
      });
    }

    // Row-stage observations are separate from both the source chain and any rowset guarantee.
    const boundary = record(w.row_boundary);
    const rowBoundary = boundary.rowset_equivalence === 'UNVERIFIED'
      ? boundary.use_prefix_status === 'STAGE_UNVERIFIED' ? 'STAGE_UNVERIFIED'
        : boundary.status === 'STAGE_UNVERIFIED'
          ? boundary.use_prefix_status === 'STAGES_OBSERVED' ? 'PREFIX_WITNESSED' : 'STAGE_UNVERIFIED'
          : undefined
      : undefined;
    return { strict_read_evidence: { ...base,
      identity: { ...identity, snapshot_id: w.snapshot_id }, status: 'WITNESSED', path_position: path,
      steps, rowBoundary, terminal: { label: `${terminal.source}.${terminal.column}`, position: last.declaration },
      ...(point.use === 'SELECT' ? {} : { limitation: 'ROWSET_EQUIVALENCE_UNVERIFIED' as const }),
    } };
  };
}
