import { useEffect, useRef, useState } from 'react';
import { analyzeSubfieldSql } from '../api/client';
import type { Port, Position, RecordRow } from './contract';
import { submittedSqlHash, type EvidenceSnapshot } from './evidenceBundle';
import type { createSQLPositionIndex } from './sqlPositionIndex';
import { outputLabel, type Output } from './taskSummary';

type Index = ReturnType<typeof createSQLPositionIndex>;
type Step = { path: string; position: Position | null };
type Proof = { source: string; steps: Step[]; projection: Position };
type State = { status: 'idle' | 'loading' | 'unavailable' } | { status: 'ready'; proof: Proof };
type Json = Record<string, unknown>;
const object = (value: unknown): Json => value && typeof value === 'object' && !Array.isArray(value) ? value as Json : {};
const list = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const samePort = (a: Json, b: Port | Json) => a.statement === b.statement && a.scope === b.scope && a.slot === b.slot;
const positionOf = (value: unknown, index: Index): Position | null => {
  const { start, end } = object(value);
  const span = typeof start === 'number' && typeof end === 'number' ? { start, end } : null;
  return index.valid(span) ? span : null;
};

function literalPath(value: unknown): string | null {
  const tokens = list(value);
  let path = '';
  for (const token of tokens.map(object)) {
    if (token.kind === 'key' && typeof token.value === 'string') {
      const key = token.value;
      path += /^[\p{L}_][\p{L}\p{N}_-]*$/u.test(key) ? (path ? '.' : '') + key : '[' + JSON.stringify(key) + ']';
    } else if (token.kind === 'index' && typeof token.value === 'number' && Number.isSafeInteger(token.value) && token.value >= 0) {
      path += '[' + token.value + ']';
    } else return null;
  }
  return path || null;
}

async function readProof(raw: unknown, snapshot: EvidenceSnapshot, output: Output, mapping: RecordRow, index: Index): Promise<Proof | null> {
  const { coverage, review } = object(raw);
  const actual = object(coverage);
  const base = object(object(snapshot.rawResponse).coverage);
  const block = object(object(review).static_extraction_evidence);
  if (block.status !== 'REVIEW_ONLY' || block.rowset_verified !== false || block.pruning_authorized !== false) return null;
  const digest = await submittedSqlHash(snapshot.request.sql);
  if (base.sql_sha256 !== digest || actual.sql_sha256 !== digest ||
      base.dialect !== snapshot.request.dialect || actual.dialect !== base.dialect ||
      typeof base.sqlglot !== 'string' || actual.sqlglot !== base.sqlglot) return null;

  const identity = (value: Json) => value.snapshot === 'local:' + digest &&
    value.sql_sha256 === digest && value.statement === output.statement && typeof value.scope === 'string' && !!value.scope;
  const port = (value: Json) => identity(value) && typeof value.slot === 'number' && Number.isSafeInteger(value.slot) && value.slot > 0;
  const root = object(block.protected_output);
  const projection = positionOf(block.projection_position, index);
  if (!port(root) || !samePort(root, output) || !projection || !mapping.position ||
      projection.start !== mapping.position.start || projection.end !== mapping.position.end ||
      !output.output || index.excerpt(projection)?.match !== output.output) return null;

  const demand = object(block.source_demand);
  const witness = list(demand.witness);
  if (demand.kind !== 'VALUE_PATH' || demand.role !== 'VALUE' || witness.length < 2 || witness.length > 8) return null;
  const source = object(demand.source);
  const mappings = list(object(snapshot.rawResponse).mappings).map(object);
  let current = root;
  const seen = new Set<string>(), steps: Step[] = [];
  for (const [i, value] of witness.entries()) {
    const edge = object(value), consumer = object(edge.consumer), evidence = object(edge.evidence);
    const id = JSON.stringify([consumer.scope, consumer.slot]);
    if (!port(consumer) || !samePort(consumer, current) || seen.has(id) || edge.role !== 'VALUE' ||
        edge.clause !== 'SELECT' || !Array.isArray(edge.operations) || evidence.origin !== 'AST_SCOPE_OCCURRENCE') return null;
    seen.add(id);
    let inputName: unknown;
    if (i < witness.length - 1) {
      current = object(edge.producer);
      if (edge.source != null || !port(current)) return null;
      const matches = mappings.filter(row => samePort(row, current));
      if (matches.length !== 1) return null;
      inputName = matches[0].output;
    } else {
      const terminal = object(edge.source);
      if (edge.producer != null || !identity(terminal) || !identity(source) ||
          terminal.scope !== consumer.scope || terminal.scope !== source.scope ||
          terminal.relation !== source.relation || terminal.column !== source.column ||
          terminal.binding !== 'SQL_NAMED_RELATION_COLUMN' || source.binding !== terminal.binding ||
          typeof source.relation !== 'string' || !source.relation || typeof source.column !== 'string' || !source.column) return null;
      inputName = terminal.column;
    }
    const [op] = edge.operations.map(object);
    if (op) {
      const path = literalPath(op.path_tokens);
      if (edge.operations.length !== 1 || op.kind !== 'EXTRACT' || !path) return null;
      const span = positionOf(evidence.position, index);
      const match = index.excerpt(span)?.match;
      const position = match && typeof inputName === 'string' && match.toLowerCase() === inputName.toLowerCase() ? span : null;
      steps.push({ path, position });
    }
  }
  if (steps.length !== 2) return null;
  steps.reverse();
  const downstream = object(demand.downstream_demand);
  if (downstream.kind !== 'VALUE_PATH' || downstream.role !== 'VALUE' ||
      literalPath(demand.path_tokens) !== steps[0].path || literalPath(downstream.path_tokens) !== steps[1].path ||
      object(downstream.downstream_demand).kind !== 'WHOLE_VALUE') return null;
  return { source: source.relation + '.' + source.column, steps, projection };
}

export function TwoStepEvidence({ snapshot, output, mapping, index, locate, clearLocation }: {
  snapshot: EvidenceSnapshot; output: Output; mapping: RecordRow; index: Index;
  locate: (position: Position) => void; clearLocation: () => void;
}) {
  const [state, setState] = useState<State>({ status: 'idle' });
  const active = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; clearLocation(); };
  }, [clearLocation]);

  async function load() {
    setState({ status: 'loading' });
    const { statement, scope, slot } = output;
    try {
      const raw = await analyzeSubfieldSql({ ...snapshot.request,
        protected_outputs: [{ statement, scope, slot }], include_two_step_evidence: true });
      const proof = active.current ? await readProof(raw, snapshot, output, mapping, index) : null;
      if (active.current) setState(proof ? { status: 'ready', proof } : { status: 'unavailable' });
    } catch {
      if (active.current) setState({ status: 'unavailable' });
    }
  }

  if (state.status === 'idle') return <button type="button" className="btn" onClick={() => void load()}>查看两步读取</button>;
  if (state.status === 'loading') return <p role="status">正在查看 {outputLabel(output)} 的两步读取证据…</p>;
  if (state.status !== 'ready') return <p role="status">本次未提供该输出的两步读取证据，路径尚未证实。你仍可查看已有读取记录；这不表示未读取。</p>;
  const { proof } = state;
  return <section aria-label="两步读取证据">
    <h4>输出 {outputLabel(output)} · 两步读取证据（SQL 静态核验）</h4>
    <p className="muted">仅证明本次 SQL 的两步读取；行集与修改影响未验证。</p>
    <p><code>{proof.source}</code> · SQL 中声明的来源列，物理存在性未验证。</p>
    <ol>{proof.steps.map(({ position, path }, i) => {
      const excerpt = index.excerpt(position);
      return <li key={i}>
        <p>{i === 0 ? '从来源值提取' : '从上一步所得值再次提取'} <code>{path}</code></p>
        {position && excerpt ? <>
          <pre className="sql">{excerpt.before}<mark>{excerpt.match}</mark>{excerpt.after}</pre>
          <button type="button" className="btn" onClick={() => locate(position)}>定位第 {i + 1} 步输入列</button>
        </> : <p className="muted">本步原文位置未提供。</p>}
      </li>;
    })}</ol>
    <button type="button" className="btn" onClick={() => locate(proof.projection)}>定位输出别名</button>
  </section>;
}
