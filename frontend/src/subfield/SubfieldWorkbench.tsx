import { lazy, memo, Suspense, useCallback, useMemo, useRef, useState } from 'react';
import { analyzeSubfieldSql } from '../api/client';
import { normalize, parseSourceSchemas, rootOutputs } from './model.mjs';
import { pathTree, projectPath } from './path-tree.mjs';
import { graphFacts } from './graph-model.mjs';
import { layeredGraphFacts } from './layered-graph.mjs';
import { ReactGraph } from './ReactGraph';
import { AnalysisReports, ReviewSummary } from './EvidenceReports';
import { layeredSQL, textMapSQL, twoJsonSQL, windowSQL } from './workbench.mjs';
import type { EvidenceOrigin, EvidenceSnapshot } from './evidenceBundle';
import { isTextMapEvidence, textMapLocations } from './textMapEvidence';
import { createSQLPositionIndex } from './sqlPositionIndex';
import { jsonReadLocation } from './jsonReadLocation';
import type { PathItem, Port, Position, RecordRow, Result } from './contract';
import './workbench.css';

const Editor = lazy(() => import('./SubfieldEditor'));
type Dialect = 'hive' | 'spark';
type Request = Parameters<typeof analyzeSubfieldSql>[0];
let localRequestSequence = 0;
const adhoc: EvidenceOrigin = { kind: 'AD_HOC' };
const constructed: EvidenceOrigin = { kind: 'CONSTRUCTED' };
type Example = { name: string; sql: string; dialect: string; note: string };
const examples: Example[] = [
  {name: '同表双 JSON 五级演示', sql: twoJsonSQL, dialect: 'spark', note: '合成示例：两列 JSON 经两级 CTE 传递。'},
  {name: '单列五级演示', sql: layeredSQL, dialect: 'spark', note: '合成示例：一列 JSON 经两级 CTE 传递。'},
  {name: '窗口与生成器示例', sql: windowSQL, dialect: 'hive', note: '合成示例：展开标签，按时间取每个标签最新的事件。'},
  {name: '单根双分支示例', dialect: 'spark', note: '构造示例：值分支不代表已验证行集。',
    sql: "WITH base AS (SELECT t.j FROM src t), l AS (SELECT get_json_object(x.j,'$.a') AS a FROM base x), r AS (SELECT get_json_object(x.j,'$.b') AS b FROM base x) SELECT COALESCE(l.a,r.b) AS protected FROM l CROSS JOIN r"},
  {name: '文本 Map 查键示例', sql: textMapSQL, dialect: 'hive', note: '合成示例：按固定键读取文本 Map 供投影和过滤。'},
];
const exampleKeys = [{ source: 'demo.events', column: 'context_json', keys: ['item_id', 'session_key', 'sample_key'] }];
const roleNames: Record<string, string> = { VALUE: '输出值依赖', CONDITION: '条件依赖', CARRIER: '载体传递', STRUCTURE: '结构依赖', RELATIONAL: '关系依赖', REPRESENTATION: '原始表示依赖' };
const pathLabel = ({ input }: PathItem) => `${input.source} · ${input.column} · ${input.path}`;

interface Branch { label: string; children: Map<string, Branch>; paths: PathItem[] }
const branch = (label: string): Branch => ({ label, children: new Map(), paths: [] });
function treeOf(paths: PathItem[]) {
  const root = branch('');
  for (const item of paths) {
    const segments = [item.input.source, item.input.column, ...(item.input.path_tokens ?? []).map(token =>
      JSON.stringify([token.kind, token.value]))];
    let parent = root;
    segments.forEach((key, i) => {
      if (!parent.children.has(key)) parent.children.set(key, branch(i < 2 ? key : key.slice(1, -1).replace(/^"key",/, '')));
      parent = parent.children.get(key)!;
    });
    parent.paths.push(item);
  }
  return root;
}
function contains(node: Branch, id?: string): boolean {
  return node.paths.some(item => item.id === id) || [...node.children.values()].some(child => contains(child, id));
}
const PathTree = memo(function PathTree({ root, active, select }: {
  root: Branch; active?: string; select: (item: PathItem) => void;
}) {
  function render(node: Branch) {
    return <details key={node.label} open={contains(node, active) || undefined}><summary>{node.label}</summary>
      <div className="json-tree-children">
        {node.paths.map(item => <button type="button" className="json-tree-row" key={item.id}
          aria-pressed={item.id === active} onClick={() => select(item)}>{item.input.path}</button>)}
        {[...node.children.values()].map(render)}
      </div>
    </details>;
  }
  return <section className="json-tree-pane" aria-label="JSON 枝干树">
    <div className="json-pane-head"><h2>JSON 枝干树</h2></div>
    {root.children.size ? [...root.children.values()].map(render) : <p className="muted">没有已绑定的源路径。</p>}
  </section>;
});

function Raw({ value, title = '查看原始服务记录' }: { value: unknown; title?: string }) {
  const [opened, setOpened] = useState(false);
  return <details onToggle={event => setOpened(event.currentTarget.open)}><summary>{title}</summary>
    {opened && <pre>{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre>}
  </details>;
}
type SQLPositionIndex = ReturnType<typeof createSQLPositionIndex>;
type EvidenceOptions = { index: SQLPositionIndex | null; locate: (range: Position) => void; declared: boolean };
function evidenceLocations(row: RecordRow, index: SQLPositionIndex | null) {
  if (isTextMapEvidence(row)) return textMapLocations(row);
  const path = jsonReadLocation(row, index);
  return path ? [{ label: '载体', position: row.position }, { label: 'JSON 路径字面量', position: path }]
    : [{ label: '', position: row.position }];
}

function EvidenceRow({ row, title, initiallyOpen, index, locate, declared }: EvidenceOptions & {
  row: RecordRow; title: string; initiallyOpen: boolean;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const locations = useMemo(() => open ? evidenceLocations(row, index).map(location => ({
    ...location, excerpt: index?.excerpt(location.position),
  })) : [], [index, open, row]);
  return <details open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>{title}</summary>
    {open && <>
      {declared && locations.some(({ excerpt }) => excerpt) &&
        <p className="muted">原件坐标未核对 · 仅定位提交 SQL</p>}
      {locations.map(({ label, position, excerpt }) => {
        const prefix = label ? label + ' · ' : '';
        if (!excerpt || !position) return <p className="muted" key={label}>{prefix}原 SQL 位置未记录。</p>;
        const line = index?.lineAt(position.start);
        return <div key={label}>
          <p className="muted">{prefix}提交 SQL 第 {line} 行</p>
          <pre className="sql">{excerpt.before}<mark>{excerpt.match}</mark>{excerpt.after}</pre>
          <button type="button" onClick={() => locate(position)}>{label ? `在编辑器定位${label}` : '在编辑器定位'}</button>
        </div>;
      })}
      <Raw value={row} />
    </>}
  </details>;
}
function Evidence({ rows, index, ...options }: EvidenceOptions & { rows: RecordRow[] }) {
  const first = rows.findIndex(row => evidenceLocations(row, index).some(({ position }) => index?.valid(position)));
  return <>{rows.map((row, i) => <EvidenceRow key={i} row={row} index={index} {...options}
    initiallyOpen={i === (first === -1 ? 0 : first)}
    title={row.role ? roleNames[row.role] ?? row.role : row.output ?? `服务证据 #${i + 1}`} />)}</>;
}

export default function SubfieldWorkbench() {
  const [sql, setSql] = useState(''), [dialect, setDialect] = useState<Dialect>('spark');
  const [schemas, setSchemas] = useState(''), [example, setExample] = useState<Example | null>(null);
  const [editorOpen, setEditorOpen] = useState(false), [location, setLocation] = useState<Position | null>(null);
  const [result, setResult] = useState<Result | null>(null), [submitted, setSubmitted] = useState('');
  const [positionIndex, setPositionIndex] = useState<SQLPositionIndex | null>(null);
  const [surface, setSurface] = useState<'table' | 'json'>('table');
  const [selected, setSelected] = useState<PathItem | null>(null), [query, setQuery] = useState('');
  const [picked, setPicked] = useState<{ title: string; rows: RecordRow[] } | null>(null);
  const [protectedSlots, setProtectedSlots] = useState<number[]>([]);
  const [candidate, setCandidate] = useState(false);
  const [review, setReview] = useState<unknown>(null), [reviewStatus, setReviewStatus] = useState('未指定保护点。');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const pending = useRef(false);
  const revision = useRef(0);
  const [analysisSnapshot, setAnalysisSnapshot] = useState<EvidenceSnapshot | null>(null);
  const [reviewSnapshot, setReviewSnapshot] = useState<EvidenceSnapshot | null>(null);
  const [downloadError, setDownloadError] = useState('');
  const [downloading, setDownloading] = useState(false);
  const writing = useRef(false);
  const inspectorEvidence = useRef<HTMLDivElement>(null);
  const paths = useMemo(() => pathTree(result), [result]);
  const tree = useMemo(() => treeOf(paths), [paths]);
  const roots = useMemo(() => rootOutputs(result?.mappings ?? []), [result]);
  const projection = useMemo(() => selected && result ? projectPath(result, selected) : null, [selected, result]);
  const fullGraph = useMemo(() => result ? (result.mappings.some(row => row.terminal_binding || row.port_reads)
    ? layeredGraphFacts(result) : graphFacts(result)) : null, [result]);
  const focusedGraph = useMemo(() => projection ? layeredGraphFacts(projection) : null, [projection]);
  const hits = useMemo(() => query.trim() ? paths.filter(path => pathLabel(path).toLowerCase().includes(query.trim().toLowerCase())).slice(0, 12) : [], [paths, query]);
  const onPick = useCallback((title: string, rows: RecordRow[]) => setPicked({ title, rows }), []);
  const onReportPick = useCallback((title: string, rows: RecordRow[]) => {
    onPick(title, rows);
    requestAnimationFrame(() => {
      inspectorEvidence.current?.scrollIntoView({ block: 'start' });
      inspectorEvidence.current?.focus({ preventScroll: true });
    });
  }, [onPick]);
  const select = useCallback((path: PathItem) => {
    setSelected(path); setPicked(null); setSurface('json'); setQuery('');
  }, []);
  function reset() {
    revision.current++;
    setPositionIndex(null);
    setAnalysisSnapshot(null); setReviewSnapshot(null); setDownloadError('');
    setResult(null); setSelected(null); setPicked(null); setQuery(''); setError('');
    setProtectedSlots([]); setReview(null); setReviewStatus('未指定保护点。'); setCandidate(false); setLocation(null);
  }
  async function requestSnapshot(request: Request, origin: EvidenceOrigin): Promise<EvidenceSnapshot> {
    const requestId = globalThis.crypto?.randomUUID?.() ?? `local-${Date.now()}-${++localRequestSequence}`;
    const capturedAt = new Date().toISOString();
    const rawResponse = await analyzeSubfieldSql(request);
    return { requestId, capturedAt, request, rawResponse, origin };
  }
  async function analyze(input = sql, mode = dialect, source = schemas, selectedExample = example) {
    if (pending.current) return;
    reset();
    if (!input.trim()) { setError('请输入 SQL 或加载示例。'); return; }
    pending.current = true; setBusy(true);
    const issued = revision.current;
    try {
      const sourceSchemas = parseSourceSchemas(source);
      const request: Request = { sql: input, dialect: mode, ...(sourceSchemas === undefined ? {} : { source_schemas: sourceSchemas }) };
      const origin = selectedExample?.sql === input ? constructed : adhoc;
      const captured = await requestSnapshot(request, origin);
      if (issued !== revision.current) return;
      const response = normalize(captured.rawResponse);
      setPositionIndex(createSQLPositionIndex(input));
      setAnalysisSnapshot(captured);
      setSubmitted(input); setResult(response); setEditorOpen(false);
    } catch (exception) { if (issued === revision.current) setError(exception instanceof Error ? exception.message : '分析失败'); }
    finally { pending.current = false; setBusy(false); }
  }
  function loadExample(example: Example, run = false) {
    const mode = example.dialect === 'hive' ? 'hive' : 'spark';
    reset(); setSql(example.sql); setDialect(mode); setSchemas(''); setExample(example);
    if (run) void analyze(example.sql, mode, '', example);
  }
  function invalidateReview() {
    revision.current++;
    setReview(null); setReviewSnapshot(null); setDownloadError('');
  }
  async function runReview() {
    if (pending.current || !analysisSnapshot) return;
    if (!protectedSlots.length) { setReviewStatus('请选择至少一个根输出。'); return; }
    pending.current = true; setBusy(true); invalidateReview(); setReviewStatus('正在评审…');
    const issued = revision.current;
    try {
      const ports: Port[] = protectedSlots.map(index => {
        const { statement, scope, slot } = roots[index]; return { statement, scope, slot };
      });
      const request: Request = { ...analysisSnapshot.request, protected_outputs: ports,
        ...(candidate && submitted === layeredSQL && dialect === 'spark' ? { candidate_keys: exampleKeys } : {}) };
      const captured = await requestSnapshot(request, analysisSnapshot.origin);
      if (issued !== revision.current) return;
      const response = normalize(captured.rawResponse);
      const hasReview = response.review !== null && typeof response.review === 'object' && !Array.isArray(response.review);
      if (hasReview) setReviewSnapshot(captured);
      setReview(hasReview ? response.review : null);
      setReviewStatus(hasReview ? '服务评审记录' : '该次响应未提供评审；可下载本次分析证据。');
    } catch (exception) {
      if (issued === revision.current) setReviewStatus(`未取得评审包；可下载本次分析证据。${exception instanceof Error ? exception.message : ''}`);
    }
    finally { pending.current = false; setBusy(false); }
  }
  const downloadSnapshot = reviewSnapshot ?? analysisSnapshot;
  async function downloadEvidence() {
    if (!downloadSnapshot || pending.current || writing.current) return;
    writing.current = true; setDownloading(true); setDownloadError('');
    const issued = revision.current;
    try {
      const { buildEvidenceBundle } = await import('./evidenceBundle');
      const bundle = await buildEvidenceBundle(downloadSnapshot);
      if (issued !== revision.current) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2) + '\n'], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `subfield-${reviewSnapshot ? 'review' : 'analysis'}-${downloadSnapshot.requestId}.json`;
      document.body.append(link);
      try { link.click(); }
      finally { link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); }
    } catch (exception) {
      if (issued === revision.current) setDownloadError(exception instanceof Error ? exception.message : '证据下载失败。');
    } finally { writing.current = false; setDownloading(false); }
  }
  const evidence = useMemo(() => picked ?? (selected && projection ? { title: pathLabel(selected), rows: [
    ...selected.uses, ...projection.mappings.flatMap(row => [row, ...(Array.isArray(row.port_reads) ? row.port_reads : [])]),
  ] } : null), [picked, selected, projection]);
  const locateEvidence = (range: Position) => {
    if (!analysisSnapshot || sql !== submitted) return;
    setLocation({ ...range });
    setEditorOpen(true);
  };
  const declared = analysisSnapshot?.origin.kind === 'EXCERPT';
  const previewEvidence = (title: string, rows: RecordRow[]) =>
    <Evidence key={title} rows={rows} index={positionIndex} declared={declared} locate={locateEvidence} />;
  const editor = editorOpen && <div id="repository-sql-editor"><Suspense fallback={<p role="status">正在加载 SQL 编辑器…</p>}>
    <Editor sql={sql} dialect={dialect} busy={busy} locate={location} positionIndex={positionIndex} run={() => void analyze()}
      setSql={value => { if (value !== sql) { reset(); setExample(null); setSql(value); } }} />
  </Suspense></div>;
  const status = result?.coverage?.partial ? '部分恢复' : result?.coverage?.parsed === false ? '解析失败'
    : result?.coverage?.parsed === true ? '完整解析' : '解析状态未提供';
  const failedStatements = result?.unknowns.filter(row => row.code === 'PARSE_ERROR') ?? [];
  const scope = analysisSnapshot?.origin.kind === 'CONSTRUCTED'
    ? '合成示例 · 仅分析本次提交 SQL' : '手动提交 SQL · 本次提交全文';
  return <div className="subfield-app">
    <section className="subfield-main" aria-label="JSON 血缘工作台">
      <form id="analysis" onSubmit={event => { event.preventDefault(); void analyze(); }}>
        <div className="actions"><button className="btn" type="button" aria-expanded={editorOpen} onClick={() => setEditorOpen(open => !open)}>编辑 SQL 原文</button>
          <label>方言 <select className="select" value={dialect} disabled={busy} onChange={event => { reset(); setDialect(event.target.value as Dialect); }}>
            <option value="spark">Spark</option><option value="hive">Hive</option>
          </select></label>
          <button className="btn-primary" type="submit" disabled={busy}>分析 SQL</button>
          <button className="btn" type="button" disabled={busy} onClick={() => loadExample(examples[0], true)}>试用示例</button>
          <label>加载示例 <select className="select" disabled={busy} value="" onChange={event => loadExample(examples[Number(event.target.value)])}>
            <option value="" disabled>选择示例</option>{examples.map((example, i) => <option key={example.name} value={i}>{example.name}</option>)}
          </select></label>
          <span role="status">{busy ? '处理中…' : result ? `服务结果 · ${result.uses.length} 个使用点` : '等待分析'}</span>
          {result && <span className="pill">{status} · {result.coverage?.complete === true ? '服务报告覆盖完整' : '覆盖未确认'} · 未决 {result.unknowns.length}</span>}
        </div>
        <details className="schema-options"><summary>源列清单（可选）</summary>
          <p className="muted">由调用方声明，未经生产数据目录核验。</p>
          <textarea aria-label="源列清单 JSON" value={schemas} disabled={busy} onChange={event => { reset(); setSchemas(event.target.value); }} />
        </details>
        {example && <p className="muted">{example.note}</p>}{error && <p id="error" role="alert">{error}</p>}
      </form>
      {result && downloadSnapshot && <section className="evidence-download" aria-label="本次分析和证据下载">
        <p>{scope}{declared && <> · 原件坐标未核对</>}</p>
        {result.coverage?.partial && <div>
          <p>已恢复语句：{result.coverage.recovered ?? '服务未提供'}</p>
          {failedStatements.map((row, i) => <p key={i}>失败语句 {typeof row.statement === 'number' ? row.statement : '编号未提供'}：
            {row.position && positionIndex?.valid(row.position) ? `提交 SQL 代码点 [${row.position.start}, ${row.position.end})` : '位置未记录'}</p>)}
        </div>}
        <div className="actions">
          <button type="button" disabled={busy || downloading} onClick={() => void downloadEvidence()}>
            {downloading ? '正在准备证据…' : '下载证据（JSON）'}
          </button>
          <p>将下载：{reviewSnapshot ? `剪枝评审证据 · 保护输出：${reviewSnapshot.request.protected_outputs?.map(port =>
            `${port.statement}/${port.scope}/${port.slot}`).join('、')}` : '分析证据'}。含提交 SQL，仅保存到本机。</p>
          {!reviewSnapshot && protectedSlots.length > 0 && <p className="muted">所选输出尚无当前评审包。</p>}
        </div>
        {downloadError && <p role="alert">{downloadError}</p>}
      </section>}
      <div className="workbench shell">
        <section className="work" aria-label="血缘画布">
          {editor}
          <div className="toolbar">
            <div className="seg canvas-mode">{(['table', 'json'] as const).map(mode =>
              <button type="button" key={mode} aria-pressed={surface === mode} onClick={() => { setSurface(mode); setPicked(null); }}>{mode === 'table' ? '表血缘' : 'JSON 排查'}</button>
            )}</div>
            <div className="search-wrap">
              <input id="canvas-search" type="search" aria-label="查找表、列或路径" placeholder="查找表、列或路径" value={query}
                onChange={event => setQuery(event.target.value)} onKeyDown={event => {
                  if (event.key === 'Escape') setQuery('');
                  if (event.key === 'Enter' && hits.length) select(hits[0]);
                  if (event.key === 'ArrowDown') { event.preventDefault(); event.currentTarget.parentElement?.querySelector('button')?.focus(); }
                }} />
              {query.trim() && <div className="results" onKeyDown={event => {
                const buttons = [...event.currentTarget.querySelectorAll('button')];
                const index = buttons.indexOf(event.target as HTMLButtonElement);
                const input = event.currentTarget.parentElement?.querySelector('input');
                if (event.key === 'Escape') { setQuery(''); input?.focus(); }
                if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                  event.preventDefault();
                  (buttons[index + (event.key === 'ArrowDown' ? 1 : -1)] ?? input)?.focus();
                }
              }}>{hits.length ? hits.map(path =>
                <button type="button" key={path.id} onClick={() => {
                  select(path);
                  requestAnimationFrame(() => document.querySelector<HTMLButtonElement>('.json-tree-row[aria-pressed=true]')?.focus());
                }}>{pathLabel(path)}</button>) : <p>未找到匹配路径</p>}
              </div>}
            </div>
          </div>
          <div className={surface === 'json' ? 'json-canvas' : undefined}>
            {surface === 'json' && <PathTree root={tree} active={selected?.id} select={select} />}
            <div className="json-flow-pane">
              {surface === 'json' && <div id="json-flow-head" className="json-pane-head">
                <h2 id="json-focus-title">{selected?.input.path ?? '从左侧选择路径'}</h2>
                {selected && <><p id="json-focus">{selected.input.source} · {selected.input.column}</p>
                  <button id="clear-path" type="button" onClick={() => { setSelected(null); setPicked(null); }}>清除路径</button></>}
              </div>}
              <ReactGraph key={surface + (selected?.id ?? '')} graph={surface === 'json' ? focusedGraph : fullGraph} onPick={onPick} />
            </div>
          </div>
          <p className="canvas-bottom">滚动查看全图 · 未决端口止步 · 点节点或连线查看证据</p>
        </section>
        <aside className="inspector" aria-label="血缘详情">
          <div className="ins-head"><h2>血缘详情</h2></div>
          <div className="ins-scroll">
            <div className="detail-body" ref={inspectorEvidence} tabIndex={-1}>
              {evidence ? <><h3>{evidence.title}</h3>
                <Evidence key={evidence.title} rows={evidence.rows} index={positionIndex} declared={declared} locate={locateEvidence} /></> : <p className="muted">选择路径、节点或连线查看服务证据。</p>}
              {result && <Raw title="本次提交 SQL" value={submitted} />}
              {result && <details open={declared || undefined}><summary>其他分析记录</summary>
                <AnalysisReports result={result} pick={onReportPick} preview={previewEvidence} />
                <Raw title="查看原始分析 JSON" value={result} />
              </details>}
            </div>
            {result && <section className="reports">
              <h2>剪枝评审</h2>
              <fieldset id="review-controls" disabled={busy}><legend>选择要保护的根输出</legend>
                <div id="protected-options">{roots.map((root, i) => <label key={i}>
                  <input type="checkbox" checked={protectedSlots.includes(i)} onChange={event => {
                    setProtectedSlots(event.target.checked ? [...protectedSlots, i] : protectedSlots.filter(slot => slot !== i));
                    invalidateReview(); setReviewStatus('保护点已更新；所选输出尚未评审。');
                  }} /> {root.output ?? '未命名'} · {root.statement}/{root.scope}/{root.slot}
                </label>)}</div>
                {!roots.length && <p>服务未提供可选根输出。</p>}
                {submitted === layeredSQL && dialect === 'spark' && <label><input type="checkbox" checked={candidate}
                  onChange={event => { setCandidate(event.target.checked); invalidateReview(); setReviewStatus('评审选项已更新；尚未评审。'); }} /> 验证示例键（含人工假设键）</label>}
                <button type="button" disabled={!roots.length} onClick={() => void runReview()}>评审剪枝</button>
              </fieldset>
              <p role="status">{reviewStatus}</p>
              {review != null && <><p>仅限当前 SQL 和所选根输出；未证明裁剪安全。未列出的路径不能据此判定为可删。</p>
                <ReviewSummary value={review} pick={onReportPick} preview={previewEvidence} />
                <Raw value={review} title="查看原始评审 JSON" /></>}
            </section>}
          </div>
        </aside>
      </div>
    </section>
  </div>;
}
