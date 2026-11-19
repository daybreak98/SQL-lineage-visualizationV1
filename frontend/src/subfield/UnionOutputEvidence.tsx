import { useEffect, useMemo, useState } from 'react';
import type { Port, Position, Result } from './contract';
import { submittedSqlHash, type EvidenceSnapshot } from './evidenceBundle';
import type { createSQLPositionIndex } from './sqlPositionIndex';
import { outputId } from './taskSummary';

type Json = Record<string, unknown>;
type Index = ReturnType<typeof createSQLPositionIndex>;
const record = (value: unknown): Json => value && typeof value === 'object' && !Array.isArray(value) ? value as Json : {};
function port(value: unknown): Port | null {
  const { statement, scope, slot } = record(value);
  return typeof statement === 'number' && Number.isSafeInteger(statement) && statement > 0 &&
    typeof scope === 'string' && scope && typeof slot === 'number' && Number.isSafeInteger(slot) && slot > 0
    ? { statement, scope, slot } : null;
}
function position(value: unknown, index: Index): Position | null {
  const { start, end } = record(value);
  const range = typeof start === 'number' && typeof end === 'number' ? { start, end } : null;
  return index.valid(range) ? range : null;
}
const portLabel = (value: Port) => `语句 ${value.statement} · ${value.scope} · 槽位 ${value.slot}`;

function readSites(result: Result, index: Index) {
  const mappings = new Map<string, Json | null>();
  for (const row of result.mappings) {
    const id = port(row);
    if (!id) continue;
    const key = outputId(id);
    mappings.set(key, mappings.has(key) ? null : row);
  }
  const raw = result.union_output_reads;
  const ids = new Set<string>();
  return (Array.isArray(raw) ? raw : []).flatMap(item => {
    const row = record(item);
    const producer = port(row.producer), consumer = port(row.consumer);
    const column = position(row.position, index);
    const argument = position(row.json_path_position, index);
    const call = position(row.call_position, index);
    const read = consumer && row.clause === 'SELECT' && row.role === 'VALUE' &&
      consumer.statement === row.statement && consumer.scope === row.scope && mappings.get(outputId(consumer));
    const control = row.consumer === null && row.clause === 'WHERE' && row.role === 'CONDITION';
    const context = record(row.select_case);
    const guard = row.consumer === null && row.clause === 'SELECT' && row.role === 'CONDITION' &&
      Array.isArray(context.parts) && context.parts.some(part => {
        const { part: kind, arm_slot } = record(part);
        return kind === 'GUARD' && typeof arm_slot === 'number' && Number.isSafeInteger(arm_slot) && arm_slot > 0;
      });
    const owner = guard ? port(context.projection) : null;
    // This is the syntactic owner of the guard, not a consumer of its value.
    const projection = owner && owner.statement === row.statement && owner.scope === row.scope &&
      mappings.get(outputId(owner)) ? owner : null;
    if (row.operation !== 'JSON_PATH_ON_UNION_SLOT' || row.value_semantics !== 'UNVERIFIED' || row.rowset_verified !== false ||
        !producer || producer.statement !== row.statement || typeof row.scope !== 'string' || !row.scope ||
        !Array.isArray(mappings.get(outputId(producer))?.union_branches) || (!read && !control && !guard) ||
        !column || !argument || !call || call.end > column.start || column.end > argument.start ||
        typeof row.column !== 'string' || index.excerpt(column)?.match.toLowerCase() !== row.column.toLowerCase() ||
        index.excerpt(call)?.match.toLowerCase() !== 'get_json_object') return [];
    const literal = index.excerpt(argument)?.match;
    if (!literal || literal.length < 2 || !["'", '"'].includes(literal[0]) || literal.at(-1) !== literal[0]) return [];
    const line = index.editorPosition(column.start);
    const id = JSON.stringify([row.statement, row.scope, row.clause, outputId(producer), column.start, column.end]);
    if (ids.has(id)) return [];
    ids.add(id);
    return [{ id, producer, consumer, projection, guard, column, argument, literal, clause: guard ? 'SELECT CASE 条件' : row.clause as 'SELECT' | 'WHERE', line }];
  });
}

export function UnionOutputEvidence({ result, snapshot, index, selectedOutput, locate }: {
  result: Result; snapshot: EvidenceSnapshot; index: Index; selectedOutput: string | null; locate: (range: Position) => void;
}) {
  const coverage = result.coverage;
  const [verified, setVerified] = useState(false);
  const [expandedOutput, setExpandedOutput] = useState<string | null>(null);
  const [chosen, setChosen] = useState<{ id: string; output: string | null } | null>(null);
  useEffect(() => {
    let active = true;
    if (typeof coverage?.sql_sha256 === 'string' && coverage.dialect === snapshot.request.dialect) {
      void submittedSqlHash(snapshot.request.sql).then(digest => {
        if (active && digest === coverage.sql_sha256) setVerified(true);
      }).catch(() => {});
    }
    return () => { active = false; };
  }, [coverage, snapshot]);
  const sites = useMemo(() => verified ? readSites(result, index) : [], [verified, result, index]);
  if (!sites.length) return null;
  const filter = selectedOutput && expandedOutput !== selectedOutput ? selectedOutput : null;
  const visible = filter ? sites.filter(item => {
    const owner = item.guard ? item.projection : item.consumer;
    return owner && outputId(owner) === filter;
  }) : sites;
  const current = visible.find(item => item.id === chosen?.id && chosen.output === filter);
  return <details key={selectedOutput ?? 'all'} open={selectedOutput ? true : undefined}>
    <summary>联合输出槽读取</summary>
    <p className="muted">读取的是联合输出槽；源分支类型转换未核验。该记录不证明物理源读取、行集或剪枝。</p>
    {filter && !visible.length && <p className="muted">此输出没有匹配的联合读取记录。</p>}
    {selectedOutput && <button type="button" className="btn" onClick={() => setExpandedOutput(filter ? selectedOutput : null)}>
      {filter ? '查看全部联合消费点' : '仅查看所选输出的读取'}
    </button>}
    <ul>{visible.map(item => <li key={item.id}><button type="button" className="btn" aria-pressed={item === current}
      onClick={() => setChosen({ id: item.id, output: filter })}>
      {item.clause} · 生产槽 {portLabel(item.producer)} · SQL 第 {item.line?.lineNumber} 行第 {item.line?.column} 列
    </button></li>)}</ul>
    {current && <section aria-label="当前联合输出槽证据">
      <p>生产槽：{portLabel(current.producer)} · 路径参数 <code>{current.literal}</code></p>
      <p>{current.guard
        ? `${current.projection ? 'CASE 投影：' + portLabel(current.projection) + '。' : 'CASE 投影未确认。'}控制用途，不计入值来源。`
        : current.consumer ? `消费输出：${portLabel(current.consumer)}` : '条件读取，没有消费输出槽。'}</p>
      <button type="button" className="btn" onClick={() => locate(current.column)}>定位读取列</button>
      <button type="button" className="btn" onClick={() => locate(current.argument)}>定位 JSON 路径字面量</button>
    </section>}
  </details>;
}
