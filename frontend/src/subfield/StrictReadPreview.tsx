import { useEffect, useId, useRef, useState } from 'react';
import type { Position } from './contract';
import { submittedSqlHash } from './evidenceBundle';
import type { createSQLPositionIndex } from './sqlPositionIndex';

type Index = ReturnType<typeof createSQLPositionIndex>;
type Use = 'SELECT' | 'WHERE' | 'ON';
type Site = { statement: number; call_position: Position };
type Point = Site & { path: string; use: Use };
export type StrictReadPoint = Point & { pathTokens: readonly { kind: 'key' | 'index'; value: string | number }[] };
type Selector = Site & { sql_sha256: string };
type Step = {
  reference: string;
  from: string;
  reference_position: Position;
  producer_position: Position;
  operation?: string;
};
type Identity = Selector & { dialect: 'spark'; version: 'preview-v1'; snapshot_id?: string };
type Reason = 'BINDING_UNVERIFIED' | 'INPUT_NOT_VISIBLE' | 'UNSUPPORTED_CHAIN' | 'BUDGET_EXCEEDED' | 'OBSERVATION_FAILED'
  | 'MIXED_REQUEST' | 'INVALID_SELECTOR' | 'SQL_HASH_MISMATCH' | 'DIALECT_UNSUPPORTED' | 'EXTERNAL_SCHEMA_UNSUPPORTED'
  | 'STATEMENT_UNSUPPORTED' | 'SITE_NOT_MATCHED' | 'SITE_NOT_UNIQUE';

// Internal view contract. The v1 loader validates wire evidence before mapping it here.
type Evidence = {
  identity: Identity;
  use: Use;
  path: string;
} & ({
  status: 'WITNESSED';
  path_position: Position;
  steps: Step[];
  terminal: { label: string; position: Position };
  limitation?: 'JOIN_PREDICATE_UNVERIFIED' | 'ROWSET_EQUIVALENCE_UNVERIFIED';
  rowBoundary?: 'PREFIX_WITNESSED' | 'STAGE_UNVERIFIED';
} | {
  status: 'UNVERIFIED';
  reason: Reason;
  local_read?: { position: Position };
  diagnostic_position?: Position;
});
export type StrictReadResponse = { strict_read_evidence?: Evidence };
export type StrictReadLoader = (request: {
  sql: string; dialect: 'spark'; strict_read_site: Selector;
}) => Promise<StrictReadResponse>;

type Props = {
  enabled?: boolean;
  submissionId: string;
  sql: string;
  dialect: string;
  index: Index;
  point: Point;
  load: StrictReadLoader;
  locate: (position: Position) => void;
  clearLocation?: () => void;
};
type State = { status: 'idle' | 'loading' | 'failed' | 'unavailable' } | { status: 'done'; evidence: Evidence };

const useLabel = { SELECT: '生成值（SELECT）', WHERE: '筛选条件（WHERE）', ON: '连接条件（ON）' };
const reasons: Record<Reason, string> = {
  BINDING_UNVERIFIED: '没有足够的绑定证据确认来源。',
  INPUT_NOT_VISIBLE: '无法确认引用关系在这处条件中可见。',
  UNSUPPORTED_CHAIN: '当前无法核对这类来源链。',
  BUDGET_EXCEEDED: '本次核对达到预算上限，未得出完整来源链。',
  OBSERVATION_FAILED: '服务未能完成本次来源观察。',
  MIXED_REQUEST: '服务无法在同一次请求中合并核对来源和其他核查。',
  INVALID_SELECTOR: '服务无法核验所选调用位置。',
  SQL_HASH_MISMATCH: '服务无法核对所选位置与提交 SQL 的身份。',
  DIALECT_UNSUPPORTED: '此方言暂不支持严格来源核对。',
  EXTERNAL_SCHEMA_UNSUPPORTED: '带外部源列声明的分析暂不支持严格来源核对。',
  STATEMENT_UNSUPPORTED: '这类 SQL 语句暂不支持严格来源核对。',
  SITE_NOT_MATCHED: '服务没有找到与所选位置匹配的读取。',
  SITE_NOT_UNIQUE: '服务无法唯一识别所选位置的读取。',
};
const samePosition = (a?: Position, b?: Position) => a != null && b != null && a.start === b.start && b.end === a.end;
const contained = (outer: Position, inner: Position) => outer.start <= inner.start && inner.end <= outer.end;

function matchingEvidence(raw: StrictReadResponse, selector: Selector, point: Point, index: Index) {
  const evidence = raw?.strict_read_evidence, identity = evidence?.identity;
  if (!evidence || !identity || identity.version !== 'preview-v1' ||
      identity.dialect !== 'spark' || identity.sql_sha256 !== selector.sql_sha256 ||
      identity.statement !== selector.statement || !samePosition(identity.call_position, selector.call_position) ||
      evidence.use !== point.use || evidence.path !== point.path) return null;
  if (evidence.status === 'WITNESSED') {
    // Never render a partial chain as a witnessed source. Direct reads may have zero hops.
    if (!identity.snapshot_id || !Array.isArray(evidence.steps) || evidence.steps.length > 32 ||
        !index.valid(evidence.path_position) || !evidence.terminal?.label || !index.valid(evidence.terminal.position) ||
        evidence.steps.some(step => !step?.reference || !step?.from || !index.valid(step.reference_position) ||
          !index.valid(step.producer_position))) return null;
    return evidence;
  }
  return evidence.status === 'UNVERIFIED' ? evidence : null;
}

export function StrictReadPreview(props: Props) {
  const { enabled = false, submissionId, sql, dialect, point, index } = props;
  if (!enabled || dialect !== 'spark' || !submissionId || !Number.isSafeInteger(point.statement) ||
      point.statement < 1 || !index.valid(point.call_position) || !point.path || Array.from(sql).length > 16_384) return null;
  return <ReadPoint key={JSON.stringify([submissionId, sql, dialect, point.statement, point.call_position.start,
    point.call_position.end, point.path, point.use])} {...props} />;
}

function ReadPoint({ sql, point, index, load, locate, clearLocation }: Props) {
  const title = useId();
  const [state, setState] = useState<State>({ status: 'idle' });
  const active = useRef(false), pending = useRef(false), located = useRef(false);
  const cleanup = useRef(clearLocation);
  cleanup.current = clearLocation;
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      if (located.current) cleanup.current?.();
    };
  }, []);

  async function request() {
    if (pending.current) return;
    pending.current = true;
    if (located.current) {
      located.current = false;
      cleanup.current?.();
    }
    setState({ status: 'loading' });
    try {
      const sql_sha256 = await submittedSqlHash(sql);
      if (!active.current) return;
      const { start, end } = point.call_position;
      const selector = { sql_sha256, statement: point.statement, call_position: { start, end } };
      const response = await load({ sql, dialect: 'spark', strict_read_site: selector });
      if (!active.current) return;
      const evidence = matchingEvidence(response, selector, point, index);
      setState(evidence ? { status: 'done', evidence } : { status: response?.strict_read_evidence === undefined ? 'unavailable' : 'failed' });
    } catch {
      if (active.current) setState({ status: 'failed' });
    } finally {
      pending.current = false;
    }
  }

  function original(range: Position, label: string) {
    const snippet = index.excerpt(range);
    if (!snippet) return <p className="muted">本项原文位置未确认。</p>;
    return <>
      <pre className="sql">{snippet.before}<mark>{snippet.match}</mark>{snippet.after}</pre>
      <button type="button" className="btn" onClick={() => { located.current = true; locate(range); }}>{label}</button>
    </>;
  }

  if (state.status === 'idle') return <button type="button" className="btn" onClick={() => void request()}>另行查证这处读取的来源</button>;
  if (state.status === 'loading') return <p role="status">正在核对这处读取…</p>;
  if (state.status === 'failed' || state.status === 'unavailable') return <div>
    <p role="status">{state.status === 'unavailable'
      ? '服务未返回本次严格读取证据，仍可查看原分析记录。' : '本次核对未完成，可重试。'}</p>
    <button type="button" className="btn" onClick={() => void request()}>重试核对</button>
  </div>;
  if (state.status !== 'done') return null;
  const evidence = state.evidence;
  const local = evidence.status === 'UNVERIFIED' ? evidence.local_read?.position : undefined;
  const hasLocal = index.valid(local) && contained(local, point.call_position);
  const isWitnessed = evidence.status === 'WITNESSED';
  return <section aria-labelledby={title}>
    <h4 id={title}>这处读取的来源</h4>
    <p>提交 SQL 第 {index.lineAt(point.call_position.start)} 行 · {point.path} · {useLabel[point.use]}</p>
    <p role="status">{isWitnessed ? '来源链已核对（仅限本次 SQL）'
      : hasLocal ? '仅确认这处读取，来源待确认' : '本项待确认'}</p>
    {isWitnessed ? original(point.call_position, '定位这处读取') : hasLocal
      ? <>{original(local, '定位这处读取')}<p>目前不能确认来自哪个源表列。</p></> : null}
    {evidence.status === 'WITNESSED' ? <>
      {evidence.steps.length > 0 && <ol>{evidence.steps.map((step, i) => <li key={i}>
        <p>本次引用：{step.reference} → 来自 {step.from}{step.operation && ` · ${step.operation}`}</p>
        {original(step.reference_position, '定位本步引用')}
        {original(step.producer_position, '定位生产列')}
      </li>)}</ol>}
      <p>SQL 声明的表列：{evidence.terminal.label}</p>
      {original(evidence.terminal.position, '定位源表列声明')}
      {evidence.rowBoundary === 'PREFIX_WITNESSED' && <p>本读点的输入前缀已核对；相关 JOIN 阶段尚未全部核对。</p>}
      {evidence.rowBoundary === 'STAGE_UNVERIFIED' && <p>本读点的静态来源已核对；相关 JOIN 阶段或输入前缀仍有待确认。</p>}
      {!evidence.rowBoundary && evidence.limitation && <p>本读点已取证；整段条件或行影响仍未验证。</p>}
    </> : <>
      <p>{Object.hasOwn(reasons, evidence.reason) ? reasons[evidence.reason] : '服务未提供可识别的未证原因。'}</p>
      {evidence.diagnostic_position && index.valid(evidence.diagnostic_position)
        ? original(evidence.diagnostic_position, '定位待确认位置')
        : !hasLocal && <p>本项原文位置未确认。</p>}
    </>}
    <button type="button" className="btn" onClick={() => void request()}>
      {isWitnessed ? '重新核对' : '重试核对'}
    </button>
    <p className="muted">{isWitnessed
      ? '只核对这处静态来源，不判断 SQL 能否运行或行集是否等价。实际目录和修改影响未验证，不提供删除授权。'
      : '仅核对本次 SQL 的静态读取；实际目录、运行结果、行集和修改影响未验证，不提供删除授权。'}</p>
  </section>;
}
