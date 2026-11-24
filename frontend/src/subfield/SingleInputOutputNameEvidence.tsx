import { useEffect, useId, useMemo, useState } from 'react';
import type { Position, RecordRow } from './contract';
import { submittedSqlHash, type EvidenceSnapshot } from './evidenceBundle';
import type { createSQLPositionIndex } from './sqlPositionIndex';

type Index = ReturnType<typeof createSQLPositionIndex>;
const obj = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const identifier = (value: unknown): value is string => typeof value === 'string' && /^[a-z_][a-z0-9_]*$/i.test(value);
const natural = (n: unknown): n is number => typeof n === 'number' && Number.isSafeInteger(n) && n > 0;
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const equal = (a: Position | null | undefined, b: Position | null | undefined) =>
  a != null && b != null && a.start === b.start && a.end === b.end;
const position = (value: unknown, index: Index): Position | null => {
  const { start, end } = obj(value);
  return typeof start === 'number' && typeof end === 'number' && index.valid({ start, end }) ? { start, end } : null;
};
const span = (value: unknown, index: Index) =>
  Array.isArray(value) && value.length === 2 ? position({ start: value[0], end: value[1] }, index) : null;
const samePort = (a: ReturnType<typeof obj>, b: ReturnType<typeof obj>) =>
  a.statement === b.statement && a.scope === b.scope && a.slot === b.slot;
function samePath(a: unknown, b: unknown) {
  return Array.isArray(a) && Array.isArray(b) && a.length > 0 && a.length === b.length &&
    b.every((token, i) => text(obj(token).kind) && obj(token).kind === obj(a[i]).kind && obj(token).value === obj(a[i]).value);
}

const EMPTY_SCHEMA = '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a';

function read(snapshot: EvidenceSnapshot, row: RecordRow, index: Index) {
  const raw = obj(snapshot.rawResponse), addon = raw.single_input_output_name_evidence;
  if (addon === undefined || row.kind !== 'EXTRACT' || row.role !== 'VALUE' || row.clause !== 'SELECT' ||
      row.path_derivation || !Array.isArray(raw.uses)) return undefined;
  const useIndex = raw.uses.indexOf(row);
  if (useIndex < 0) return undefined;
  const block = obj(addon), { witnesses } = block;
  const call = position(row.position, index), literal = position(row.json_path_position, index);
  if (!Array.isArray(witnesses) || !witnesses.length || witnesses.length > 64) return null;
  const matches = witnesses.map(obj).filter(w => w.use_index === useIndex || equal(span(w.call_span, index), call));
  if (!matches.length) return undefined;
  const w = matches[0], stamp = obj(block.snapshot), coverage = obj(raw.coverage);
  const anchor = obj(w.anchor), consumer = obj(w.consumer), producer = obj(w.producer), relation = obj(w.relation);
  if (matches.length !== 1 || block.version !== 'single-input-output-name:1' || block.rules !== 'spark:local-cte-slot:1' ||
      block.basis !== 'SAME_RUN_SINGLE_INPUT_CTE_SLOT' || block.catalog_verified !== false ||
      snapshot.request.dialect !== 'spark' || snapshot.request.source_schemas !== undefined ||
      stamp.dialect !== 'spark' || coverage.dialect !== stamp.dialect || stamp.schema_sha256 !== EMPTY_SCHEMA ||
      !text(stamp.id) || !text(stamp.sqlglot) || stamp.sqlglot !== coverage.sqlglot ||
      !text(stamp.sql_sha256) || stamp.sql_sha256 !== coverage.sql_sha256 ||
      w.use_index !== useIndex || !call || !literal || !equal(span(w.call_span, index), call) ||
      !equal(span(w.literal_span, index), literal) || !samePath(w.path_tokens, row.path_tokens) ||
      anchor.kind !== 'SINGLE_INPUT_OUTPUT_NAME' || Object.hasOwn(anchor, 'qualifier_span') ||
      !natural(row.statement) || consumer.statement !== row.statement || producer.statement !== row.statement ||
      !text(consumer.scope) || !text(producer.scope) || relation.scope !== consumer.scope || producer.scope === consumer.scope ||
      !natural(consumer.slot) || !natural(producer.slot) || !Array.isArray(raw.mappings)) return null;

  const column = span(anchor.column_span, index), output = span(producer.output_name_span, index);
  const cte = span(producer.cte_name_span, index), reference = span(relation.reference_name_span, index);
  const declaration = span(relation.declaration_span, index);
  if (!column || !output || !cte || !reference || !declaration ||
      column.start < call.end || column.end > literal.start || cte.end > output.start || output.end > call.start ||
      literal.end > reference.start || declaration.start < reference.start ||
      (declaration.start !== reference.start && declaration.start < reference.end) ||
      (declaration.start === reference.start && !equal(declaration, reference))) return null;

  const columnName = index.excerpt(column)?.match, outputName = index.excerpt(output)?.match;
  const cteName = index.excerpt(cte)?.match, referenceName = index.excerpt(reference)?.match;
  if (!identifier(columnName) || !identifier(outputName) || outputName.toLowerCase() !== columnName.toLowerCase() ||
      !identifier(cteName) || !identifier(referenceName) || referenceName.toLowerCase() !== cteName.toLowerCase() ||
      !identifier(index.excerpt(declaration)?.match)) return null;

  // Ordinary resolver ports independently tie these exact spans to this consumer and producer.
  const mappings = raw.mappings.map(obj);
  const roots = mappings.filter(m => m.root === true && m.target === null && samePort(m, consumer));
  const slots = mappings.filter(m => m.root === false && samePort(m, producer));
  if (roots.length !== 1 || slots.length !== 1 || slots[0].output !== outputName ||
      !equal(position(slots[0].position, index), output) || !Array.isArray(roots[0].port_reads)) return null;
  const reads = roots[0].port_reads.map(obj).filter(r => r.kind === 'EXTRACT' &&
    equal(position(r.position, index), column) && equal(position(r.json_path_position, index), literal) &&
    samePath(r.path_tokens, row.path_tokens) && samePort(obj(r.producer), producer));
  if (reads.length !== 1) return null;
  return { column, output, label: cteName + '.' + outputName, slot: producer.slot, sqlSha256: stamp.sql_sha256 };
}

export function SingleInputOutputNameEvidence({ snapshot, row, index, locate }: {
  snapshot: EvidenceSnapshot; row: RecordRow; index: Index; locate: (range: Position) => void;
}) {
  const title = useId();
  const proof = useMemo(() => read(snapshot, row, index), [snapshot, row, index]);
  const [verified, setVerified] = useState<typeof proof>(undefined);
  useEffect(() => {
    if (!proof) return;
    let current = true;
    void submittedSqlHash(snapshot.request.sql).then(hash => {
      if (current) setVerified(hash === proof.sqlSha256 ? proof : null);
    }).catch(() => { if (current) setVerified(null); });
    return () => { current = false; };
  }, [snapshot, proof]);
  if (proof === undefined) return null;
  return <section aria-labelledby={title}>
    <h4 id={title}>单输入 CTE 输出名证据</h4>
    {proof && proof === verified ? <>
      <p role="status">单输入 CTE 已核对</p>
      <p>唯一匹配的 CTE 声明输出：<code>{proof.label}</code>（第 {proof.slot} 槽）</p>
      <p>这里只核对 SQL 中的输出名绑定，不核对读取值、行集或剪枝安全。</p>
      <button type="button" className="btn" onClick={() => locate(proof.column)}>定位读取处的列名</button>
      <button type="button" className="btn" onClick={() => locate(proof.output)}>定位 CTE 输出名声明</button>
    </> : <p role="status">本项待确认</p>}
  </section>;
}
