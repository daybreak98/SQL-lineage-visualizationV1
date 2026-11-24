import { LocateAction } from './WorkbenchAnnotations';
import { useEffect, useId, useRef, useState } from 'react';
import type { Position, RecordRow } from './contract';
import { submittedSqlHash, type EvidenceSnapshot } from './evidenceBundle';
import type { createSQLPositionIndex } from './sqlPositionIndex';

type Index = ReturnType<typeof createSQLPositionIndex>;
type Json = Record<string, unknown>;
type Chain = { conditional: boolean; steps: { label: string; position: Position; producer?: Position }[]; source: string; terminal: Position };
const REF = 'SQL_CTE_RELATION_CHAIN_REF';
const MAX_ENTRIES = 4096;
const EMPTY_SCHEMA = '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a';
const record = (v: unknown): Json => v != null && typeof v === 'object' && !Array.isArray(v) ? v as Json : {};
const integer = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const at = (list: unknown[], ref: unknown) => integer(ref) && ref >= 0 && ref < list.length ? record(list[ref]) : {};
const has = (value: Json, ...keys: string[]) => keys.some(key => Object.hasOwn(value, key));
export const hasCompactReadRef = (row: RecordRow) => record(row.named_source_binding).kind === REF;

function readPosition(value: unknown, index: Index) {
  const { start, end } = record(value);
  const range = integer(start) && integer(end) ? { start, end } : null;
  return index.valid(range) ? range : null;
}

async function decode(snapshot: EvidenceSnapshot, row: RecordRow, index: Index): Promise<Chain | null> {
  const raw = record(snapshot.rawResponse), coverage = record(raw.coverage);
  const wire = record(raw.strict_use_evidence), identity = record(wire.snapshot);
  const ref = record(row.named_source_binding), { instances, tails } = wire;
  const { request } = snapshot;
  if (ref.kind !== REF || row.kind !== 'EXTRACT' || row.path_derivation ||
      !Array.isArray(raw.uses) || !raw.uses.includes(row) ||
      wire.version !== 2 || (wire.status !== 'ATTACHED' && wire.status !== 'BUDGET_EXCEEDED') ||
      (wire.status === 'BUDGET_EXCEEDED' && wire.reason !== 'WIRE_BYTES' && wire.reason !== 'CHAIN_HOPS') ||
      !Array.isArray(instances) || !Array.isArray(tails) || instances.length > MAX_ENTRIES || tails.length > MAX_ENTRIES ||
      request.dialect !== 'spark' || request.source_schemas !== undefined || identity.schema_sha256 !== EMPTY_SCHEMA ||
      identity.dialect !== request.dialect || identity.dialect !== coverage.dialect ||
      !text(identity.sqlglot) || identity.sqlglot !== coverage.sqlglot || !text(identity.rules) ||
      !text(identity.sql_sha256) || identity.sql_sha256 !== coverage.sql_sha256 ||
      !integer(row.statement) || row.statement < 1 || !text(ref.scope) ||
      has(ref, 'relation_instance', 'via', 'via_version', 'terminal_column_position', 'terminal_qualifier_position')) return null;
  const conditional = has(ref, 'identity_condition', 'row_boundary');
  if (conditional && (ref.identity_condition !== 'ON_ROWS_PRODUCED_BY_SLOT' ||
      record(ref.row_boundary).status !== 'STAGE_UNVERIFIED')) return null;
  if (await submittedSqlHash(request.sql) !== identity.sql_sha256) return null;
  const call = readPosition(row.position, index), path = readPosition(row.json_path_position, index);
  const context = record(ref.head_context);
  const tail = at(tails, ref.tail_ref);
  const via = tail.via;
  if (!call || !path || index.excerpt(call)?.match.toLowerCase() !== 'get_json_object' ||
      (ref.head_context !== undefined && (!Object.keys(context).length || Object.keys(context).some(k => k !== 'join_visibility'))) ||
      Object.keys(tail).some(k => !['via', 'relation_instance', 'terminal_column_position', 'terminal_qualifier_position'].includes(k)) ||
      !Array.isArray(via) || via.length < 1 || via.length >= 8 || Object.keys(record(via[0])).some(k => k !== 'producer')) return null;

  const consumer = record(ref.consumer);
  if (row.role === 'VALUE') {
    if (row.clause !== 'SELECT' || consumer.scope !== ref.scope || consumer.statement !== row.statement ||
        !integer(consumer.slot) || consumer.slot < 1 || has(ref, 'operator_position')) return null;
  } else if (has(ref, 'consumer') || !readPosition(ref.operator_position, index)) return null;

  const seen = new Set<unknown>();
  const read = (instanceRef: unknown, proof: Json, scope: string, visibility: unknown) => {
    if (seen.has(instanceRef)) return null;
    seen.add(instanceRef);
    const instance = at(instances, instanceRef);
    const declaration = readPosition(instance.declaration_position, index);
    const column = readPosition(proof.column_position, index), qualifier = readPosition(proof.qualifier_position, index);
    if (instance.statement !== row.statement || instance.declaration_scope !== scope ||
        !text(instance.name) || !declaration || !column || !qualifier || qualifier.end > column.start ||
        !Array.isArray(instance.table_part_positions) || !instance.table_part_positions.length ||
        instance.table_part_positions.some(position => !readPosition(position, index))) return null;
    if (visibility !== undefined) {
      const { ordinal, on_position, prefix_declarations } = record(visibility);
      if (!integer(ordinal) || ordinal < 1 || !readPosition(on_position, index) ||
          !Array.isArray(prefix_declarations) || !prefix_declarations.length || prefix_declarations.length > 33 ||
          prefix_declarations.some(position => !readPosition(position, index)) ||
          !prefix_declarations.some(position => {
            const span = readPosition(position, index);
            return span?.start === declaration.start && span.end === declaration.end;
          })) return null;
    }
    const position = { start: qualifier.start, end: column.end };
    const label = index.excerpt(position)?.match;
    const relation = instance.table_part_positions.map(part => index.excerpt(readPosition(part, index))?.match).join('.');
    return label ? { label, position, column, declaration, relation } : null;
  };

  let scope = ref.scope;
  const steps: Chain['steps'] = [];
  const scopes = new Set([scope]);
  for (const [i, item] of via.entries()) {
    const hop = record(item), producer = record(hop.producer);
    if (has(hop, 'instance_ref', 'tail_ref', 'head_context') || producer.statement !== row.statement ||
        !text(producer.scope) || scopes.has(producer.scope) || !integer(producer.slot) || producer.slot < 1) return null;
    const node = i === 0 ? read(ref.instance_ref, ref, scope, context.join_visibility)
      : read(hop.relation_instance, hop, scope, hop.join_visibility);
    if (!node || (i === 0 && (node.position.start < call.end || node.position.end > path.start))) return null;
    if (steps.length) steps[steps.length - 1].producer = node.column;
    steps.push(node);
    scope = producer.scope;
    scopes.add(scope);
  }

  const terminal = read(tail.relation_instance, { column_position: tail.terminal_column_position,
    qualifier_position: tail.terminal_qualifier_position }, scope, ref.terminal_join_visibility);
  const sourceColumn = index.excerpt(terminal?.column)?.match;
  if (!terminal || !sourceColumn) return null;
  steps[steps.length - 1].producer = terminal.column;
  steps.push(terminal);
  return { conditional, steps, source: terminal.relation + '.' + sourceColumn, terminal: terminal.declaration };
}

type Props = { snapshot: EvidenceSnapshot; row: RecordRow; index: Index;
  locate: (position: Position) => void; clearLocation: () => void };
export function CompactReadEvidence(props: Props) {
  const { snapshot, row } = props;
  return <SelectedRead key={JSON.stringify([snapshot.requestId, row.statement, row.position?.start, row.position?.end])} {...props} />;
}

function SelectedRead({ snapshot, row, index, locate, clearLocation }: Props) {
  const title = useId();
  const [expanded, setExpanded] = useState(false);
  const [result, setResult] = useState<{ snapshot: EvidenceSnapshot; row: RecordRow; chain: Chain | null }>();
  const located = useRef(false);
  useEffect(() => {
    let active = true;
    if (!expanded) return;
    void decode(snapshot, row, index).catch(() => null).then(chain => { if (active) setResult({ snapshot, row, chain }); });
    return () => {
      active = false;
      if (located.current) { located.current = false; clearLocation(); }
    };
  }, [expanded, snapshot, row, index, clearLocation]);
  const chain = result?.snapshot === snapshot && result.row === row ? result.chain : undefined;

  const atSql = (position: Position, name: string, producer = false) =>
    <LocateAction label={name} producer={producer} onClick={() => { located.current = true; locate(position); }} />;
  const coordinates = (position: Position) => {
    const at = index.editorPosition(position.start);
    return at ? at.lineNumber + ':' + at.column : '位置未确认';
  };
  if (!expanded) return <button type="button" className="btn" onClick={() => setExpanded(true)}>展开本次来源证据</button>;
  return <section aria-labelledby={title}>
    <h4 id={title}>这处读取的来源</h4>
    {chain === undefined ? <p role="status">正在核对这处读取…</p> : !chain ? <p role="status">本项待确认</p> : <>
      {chain.conditional ? <>
        <p role="status">若此读点被求值，其输入来源为 {chain.source}</p>
        <p>上游 JOIN 行边界未核对</p>
      </> : <p role="status">来源链已核对（仅限本次 SQL）</p>}
      <p>{row.clause === 'SELECT' && row.role === 'VALUE' ? '生成值（SELECT）' :
        row.clause === 'WHERE' ? '筛选条件（WHERE，不计入值来源）' :
        row.clause === 'JOIN' ? '连接条件（ON，不计入值来源）' : '控制用途，不计入值来源'} · {String(row.path ?? '')}</p>
      <ol className="j-compact-steps">{chain.steps.map((step, i) => <li key={step.position.start}>
        <div className="j-inline-note"><code>{step.label}</code>
          {atSql(step.position, `定位第 ${i + 1} 跳引用：${step.label}`)} <span>引用 · {coordinates(step.position)}</span>
          {step.producer && <>{atSql(step.producer, `定位第 ${i + 1} 跳生产列：${index.excerpt(step.producer)?.match}`, true)}
            <span>生产列 · {coordinates(step.producer)}</span></>}
        </div>
      </li>)}</ol>
      <div className="j-inline-note">{!chain.conditional && <span>SQL 声明的表列：{chain.source}</span>}
        {atSql(chain.terminal, '定位源表声明')} <span>声明 · {coordinates(chain.terminal)}</span></div>
      <p className="muted">只核对这处静态来源，不判断 SQL 能否运行或行集是否等价，不提供删除授权。</p>
    </>}
  </section>;
}
