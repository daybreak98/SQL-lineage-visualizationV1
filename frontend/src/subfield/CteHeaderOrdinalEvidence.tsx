import { useEffect, useId, useMemo, useState } from 'react';
import type { Position, RecordRow } from './contract';
import { submittedSqlHash, type EvidenceSnapshot } from './evidenceBundle';
import type { createSQLPositionIndex } from './sqlPositionIndex';
import { LocateAction } from './WorkbenchAnnotations';

type Index = ReturnType<typeof createSQLPositionIndex>;
const rec = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value)
  ? value as Record<string, unknown> : {};
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const positive = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v > 0;
const identifier = (v: unknown): v is string => typeof v === 'string' && /^[a-z_][a-z0-9_]*$/i.test(v);
const equal = (a: Position | null, b: Position | null) => !!a && !!b && a.start === b.start && a.end === b.end;
const samePort = (a: ReturnType<typeof rec>, b: ReturnType<typeof rec>) =>
  a.statement === b.statement && a.scope === b.scope && a.slot === b.slot;
const EMPTY_SCHEMA = '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a';

function read(snapshot: EvidenceSnapshot, row: RecordRow, index: Index) {
  const raw = rec(snapshot.rawResponse), addon = raw.cte_header_ordinal_evidence;
  if (addon === undefined || row.kind !== 'EXTRACT' || row.role !== 'VALUE' || row.clause !== 'SELECT' ||
      row.path_derivation || !Array.isArray(raw.uses)) return undefined;
  const useIndex = raw.uses.indexOf(row);
  if (useIndex < 0) return undefined;
  const { sql, dialect, source_schemas } = snapshot.request;
  const position = (v: unknown) => {
    const { start, end } = rec(v);
    return typeof start === 'number' && typeof end === 'number' && index.valid({ start, end }) ? { start, end } : null;
  };
  const span = (v: unknown) => Array.isArray(v) && v.length === 2 ? position({ start: v[0], end: v[1] }) : null;
  const slice = (start: number, end: number) => {
    const l = index.utf16Offset(start), r = index.utf16Offset(end);
    return l !== null && r !== null && l <= r ? sql.slice(l, r) : '';
  };
  const token = (p: Position | null) => p && slice(p.start, p.end);
  const matchesPath = (v: unknown) => Array.isArray(v) && Array.isArray(row.path_tokens) && v.length > 0 &&
    v.length === row.path_tokens.length && row.path_tokens.every((item, i) =>
      text(rec(item).kind) && rec(item).kind === rec(v[i]).kind && rec(item).value === rec(v[i]).value);
  const block = rec(addon), stamp = rec(block.snapshot), coverage = rec(raw.coverage);
  const call = position(row.position), literal = position(row.json_path_position);
  if (!Array.isArray(block.witnesses) || !block.witnesses.length || block.witnesses.length > 64) return null;
  const matches = block.witnesses.map(rec).filter(w => w.use_index === useIndex || equal(span(w.call_span), call));
  if (!matches.length) return undefined;
  const w = matches[0], producer = rec(w.producer), consumer = rec(w.consumer), terminal = rec(w.terminal);
  if (matches.length !== 1 || w.use_index !== useIndex || w.kind !== 'CTE_HEADER_ORDINAL_PASSTHROUGH' ||
      block.version !== 'cte-header-path-shadow:1' || block.rules !== 'spark:cte-header-ordinal:1' ||
      block.basis !== 'SAME_RUN_ACTUAL_CTE_HEADER_SLOT' || block.catalog_verified !== false || block.pruning_authorized !== false ||
      block.value_equivalence !== 'UNVERIFIED' || block.rowset_equivalence !== 'UNVERIFIED' ||
      dialect !== 'spark' || source_schemas !== undefined || stamp.dialect !== dialect || stamp.dialect !== coverage.dialect ||
      stamp.schema_sha256 !== EMPTY_SCHEMA || !text(stamp.id) || !text(stamp.sql_sha256) ||
      stamp.sql_sha256 !== coverage.sql_sha256 || !text(stamp.sqlglot) || stamp.sqlglot !== coverage.sqlglot ||
      !positive(row.statement) || consumer.statement !== row.statement || producer.statement !== row.statement ||
      !text(consumer.scope) || !text(producer.scope) || consumer.scope === producer.scope ||
      !positive(consumer.slot) || !positive(producer.slot) || !call || !literal ||
      !equal(call, span(w.call_span)) || !equal(literal, span(w.literal_span)) || !matchesPath(w.path_tokens) ||
      !Array.isArray(raw.mappings)) return null;

  const cte = span(w.cte_name_span), header = span(w.header_name_span), inner = span(w.producer_name_span);
  const qual = span(w.qualifier_span), column = span(w.column_span), input = span(w.input_declaration_span);
  const base = span(terminal.declaration_span), baseQual = span(terminal.qualifier_span), baseColumn = span(terminal.column_span);
  if (!cte || !header || !inner || !qual || !column || !input || !base || !baseQual || !baseColumn ||
      cte.end > header.start || header.end > baseQual.start || baseQual.end > baseColumn.start ||
      (!equal(inner, baseColumn) && baseColumn.end >= inner.start) ||
      inner.end > base.start || base.end > call.start || call.end > qual.start || qual.end > column.start ||
      column.end > literal.start || literal.end > input.start) return null;

  const [cteName, headerName, innerName, qualifier, columnName, baseName, baseQualifier, baseColumnName, inputName] =
    [cte, header, inner, qual, column, base, baseQual, baseColumn, input].map(token);
  if (!identifier(cteName) || !identifier(headerName) || !identifier(innerName) ||
      !identifier(qualifier) || !identifier(columnName) || !identifier(baseName) ||
      !identifier(baseQualifier) || !identifier(baseColumnName) || !identifier(inputName) ||
      headerName.toLowerCase() !== columnName.toLowerCase() || qualifier.toLowerCase() !== inputName.toLowerCase() ||
      baseQualifier.toLowerCase() !== baseName.toLowerCase() || baseColumnName !== terminal.column ||
      baseColumnName !== row.column || terminal.source !== row.source || !text(row.source) ||
      !/^\s*\.\s*$/.test(slice(qual.end, column.start)) || !/^\s*\.\s*$/.test(slice(baseQual.end, baseColumn.start)) ||
      (!equal(inner, baseColumn) && !/^\s+(?:AS\s+)?$/i.test(slice(baseColumn.end, inner.start)))) return null;

  // Only inspect the anchored identifier list; never derive a lineage edge by name.
  const declaration = /^\s*\(([a-z0-9_,\s]+)\)\s+AS\s*\(/i.exec(slice(cte.end, baseQual.start));
  const declaredNames = declaration ? [...declaration[1].matchAll(/[a-z_][a-z0-9_]*/gi)] : [];
  const target = declaredNames[producer.slot - 1];
  const headStart = declaration && target
    ? cte.end + Array.from(declaration[0].slice(0, declaration[0].indexOf('(') + 1) + declaration[1].slice(0, target.index)).length : -1;
  if (!target || headStart !== header.start || headStart + target[0].length !== header.end ||
      !/\bWITH\s*$/i.test(slice(0, cte.start))) return null;

  const mappings = raw.mappings.map(rec);
  const roots = mappings.filter(m => m.root === true && samePort(m, consumer));
  const outputs = mappings.filter(m => m.root === false && samePort(m, producer));
  if (roots.length !== 1 || outputs.length !== 1 || !Array.isArray(roots[0].port_reads) ||
      outputs[0].kind !== 'WHOLE_RAW' || !text(outputs[0].output) ||
      outputs[0].output.toLowerCase() !== headerName.toLowerCase() ||
      !Array.isArray(outputs[0].inputs) || outputs[0].inputs.length !== 1 ||
      rec(outputs[0].inputs[0]).source !== row.source || rec(outputs[0].inputs[0]).column !== row.column) return null;
  const edges = roots[0].port_reads.map(rec).filter(e => e.kind === 'EXTRACT' && samePort(rec(e.producer), producer) &&
    equal(position(e.position), column) && equal(position(e.json_path_position), literal) && matchesPath(e.path_tokens));
  if (edges.length !== 1) return null;
  const expression = baseQualifier + '.' + baseColumnName + (equal(inner, baseColumn) ? '' : ' AS ' + innerName);
  const shownExpression = (v: unknown) => text(v) ? v.toLowerCase().replace(/\s+/g, '') : '';
  const producerExpression = shownExpression(expression);
  if (shownExpression(outputs[0].expression) !== producerExpression ||
      mappings.filter(m => m.root === false && m.statement === producer.statement && m.scope === producer.scope &&
        shownExpression(m.expression) === producerExpression).length !== 1) return null;
  const owner = position(roots[0].position);
  const from = (source: string, alias: string, p: Position, after: number) => {
    const parts = source.split('.');
    if (!parts.every(identifier)) return false;
    const table = parts.join('\\s*\\.\\s*');
    const suffix = '(?:\\s+(?:AS\\s+)?' + alias + ')';
    return new RegExp('\\bFROM\\s+' + table + suffix + (parts.at(-1)?.toLowerCase() === alias.toLowerCase() ? '?' : '') + '$', 'i')
      .test(slice(after, p.end));
  };
  if (!owner || owner.start < literal.end || owner.end >= input.start ||
      !from(cteName, inputName, input, owner.end) || !from(row.source, baseName, base, inner.end)) return null;

  return { header, inner, declaredName: cteName + '.' + headerName, innerName, slot: producer.slot, hash: stamp.sql_sha256 };
}

export function CteHeaderOrdinalEvidence({ snapshot, row, index, locate }: {
  snapshot: EvidenceSnapshot; row: RecordRow; index: Index; locate: (range: Position) => void;
}) {
  const title = useId();
  const candidate = useMemo(() => read(snapshot, row, index), [snapshot, row, index]);
  const [proof, setProof] = useState<typeof candidate>(undefined);
  useEffect(() => {
    if (!candidate) return;
    let active = true;
    void submittedSqlHash(snapshot.request.sql).then(hash => {
      if (active) setProof(hash === candidate.hash ? candidate : null);
    }).catch(() => { if (active) setProof(null); });
    return () => { active = false; };
  }, [snapshot, candidate]);
  if (candidate === undefined) return null;
  const coordinate = (p: Position) => {
    const point = index.editorPosition(p.start);
    return point && point.lineNumber + ':' + point.column;
  };
  return <section aria-labelledby={title}>
    <h4 id={title}>CTE 声明列证据</h4>
    {proof && proof === candidate ? <>
      <p role="status">CTE 列序已核对</p>
      <div className="j-inline-note">声明第 {proof.slot} 列 <code>{proof.declaredName}</code> · {coordinate(proof.header)}
        <LocateAction label="定位 CTE 声明列" onClick={() => locate(proof.header)} />
      </div>
      <div className="j-inline-note">内部生产名 <code>{proof.innerName}</code> · {coordinate(proof.inner)}
        <LocateAction label="定位内部生产名" producer onClick={() => locate(proof.inner)} />
      </div>
      <p>静态列序证据 · 目录、值与行集未验 · 无删除授权</p>
    </> : <p role="status">本项待确认</p>}
  </section>;
}
