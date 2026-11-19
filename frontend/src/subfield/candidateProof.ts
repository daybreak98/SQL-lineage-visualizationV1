import type { Port, Position } from './contract';
import { submittedSqlHash, type EvidenceSnapshot } from './evidenceBundle';
import type { createSQLPositionIndex } from './sqlPositionIndex';
import type { Candidate } from './taskSummary';

type Index = ReturnType<typeof createSQLPositionIndex>;
type Json = Record<string, unknown>;
export type CandidateProof = { path: string; filterColumn: string; valuePosition: Position | null; predicate: Position | null };

const object = (value: unknown): Json => value && typeof value === 'object' && !Array.isArray(value) ? value as Json : {};
function position(value: unknown, index: Index) {
  const { start, end } = object(value);
  const result = typeof start === 'number' && typeof end === 'number' ? { start, end } : null;
  return index.valid(result) ? result : null;
}
function samePort(value: unknown, port: Port) {
  const { statement, scope, slot } = object(value);
  return statement === port.statement && scope === port.scope && slot === port.slot;
}

export async function readCandidateProof(base: EvidenceSnapshot, captured: EvidenceSnapshot, candidate: Candidate,
  index: Index | null): Promise<CandidateProof | null> {
  const response = object(captured.rawResponse);
  const review = object(response.review);
  const proof = object(review.observed_candidate_read);
  const { request } = captured;
  const port = request.protected_outputs?.[0];
  if (!index || !port || request.protected_outputs?.length !== 1 || request.dialect !== 'spark' ||
      request.dialect !== base.request.dialect || request.sql !== base.request.sql ||
      request.source_schemas !== undefined || base.request.source_schemas !== undefined ||
      review.status !== 'REVIEW_ONLY' || !Array.isArray(review.protected_outputs) ||
      review.protected_outputs.length !== 1 || !samePort(review.protected_outputs[0], port) ||
      proof.status !== 'OBSERVED' || proof.basis !== 'LOCAL_VALUE_READ_ONLY' ||
      proof.rowset_verified !== false || proof.pruning_authorized !== false) return null;

  const identity = object(proof.analysis);
  const original = object(object(base.rawResponse).coverage), current = object(response.coverage);
  if (identity.rule !== 'SINGLE_SOURCE_FILTER_EQ_V1' || identity.schema_basis !== 'SQL_NAMED_RELATIONS' ||
      identity.dialect !== request.dialect || current.dialect !== identity.dialect || original.dialect !== identity.dialect ||
      typeof identity.sqlglot !== 'string' || original.sqlglot !== identity.sqlglot || current.sqlglot !== identity.sqlglot ||
      typeof identity.sql_sha256 !== 'string' || original.sql_sha256 !== identity.sql_sha256 ||
      current.sql_sha256 !== identity.sql_sha256) return null;
  const digest = await submittedSqlHash(request.sql).catch(() => null);
  if (digest !== identity.sql_sha256) return null;

  const value = object(proof.value), control = object(proof.control);
  const alias = position(value.relation_alias_position, index), filterAlias = position(control.relation_alias_position, index);
  if (!samePort(value.port, port) || value.source !== candidate.source || value.column !== candidate.column ||
      value.role !== 'VALUE' || value.clause !== 'SELECT' ||
      control.statement !== port.statement || control.scope !== port.scope || control.source !== value.source ||
      control.role !== 'CONDITION' || control.clause !== 'WHERE' || control.consumer !== 'ROW_FILTER' || control.operator !== 'EQ' ||
      typeof control.column !== 'string' || !control.column || control.column === candidate.column ||
      typeof value.relation_alias !== 'string' || value.relation_alias !== control.relation_alias ||
      !alias || !filterAlias || alias.start !== filterAlias.start || alias.end !== filterAlias.end ||
      index.excerpt(alias)?.match.toLowerCase() !== value.relation_alias.toLowerCase()) return null;

  const tokens = Array.isArray(value.path_tokens) ? value.path_tokens.map(object) : [];
  const keys: string[] = [];
  for (const token of tokens) {
    if (token.kind !== 'key' || typeof token.value !== 'string') return null;
    keys.push(token.value);
  }
  if (keys[0] !== candidate.key) return null;
  const path = '$' + keys.map(key => /^[\p{L}_][\p{L}\p{N}_-]*$/u.test(key) ? '.' + key : '[' + JSON.stringify(key) + ']').join('');

  const call = position(value.position, index), column = position(value.column_position, index);
  const valuePosition = call && column && call.end <= column.start &&
    index.excerpt(call)?.match.toLowerCase() === 'get_json_object' &&
    index.excerpt(column)?.match.toLowerCase() === candidate.column.toLowerCase() ? call : null;
  const predicateSpan = position(control.predicate_span, index);
  const controlColumn = position(control.position, index), literal = position(control.literal_position, index);
  const predicate = predicateSpan && controlColumn && literal && predicateSpan.start <= controlColumn.start &&
    controlColumn.end <= literal.start && literal.end === predicateSpan.end &&
    index.excerpt(controlColumn)?.match.toLowerCase() === control.column.toLowerCase() ? predicateSpan : null;
  return { path, filterColumn: control.column, valuePosition, predicate };
}
