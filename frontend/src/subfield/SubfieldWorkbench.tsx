import { lazy, memo, Suspense, useCallback, useMemo, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { Splitter } from '../components/Splitter';
import { analyzeSubfieldSql } from '../api/client';
import { normalize, parseSourceSchemas, rootOutputs } from './model.mjs';
import { pathTree, projectPath } from './path-tree.mjs';
import { graphFacts } from './graph-model.mjs';
import { layeredGraphFacts } from './layered-graph.mjs';
import { ReactGraph } from './ReactGraph';
import { AnalysisReports, ReviewSummary } from './EvidenceReports';
import { layeredSQL, twoJsonSQL } from './workbench.mjs';
import archive from './archive-example.json';
import coupon from './coupon-window-example.json';
import archiveEvidence from './archive-evidence-examples.json';
import type { EvidenceOrigin, EvidenceSnapshot } from './evidenceBundle';
import { isTextMapEvidence, textMapLocations } from './textMapEvidence';
import { readSqlFile, sqlPreviewLimitLabel, type LocalSqlFile } from './sqlFile';
import { LongSqlExcerpt } from './LongSqlExcerpt';
import { createSQLPositionIndex } from './sqlPositionIndex';
import { jsonReadLocation, preferredJsonReadLocation } from './jsonReadLocation';
import type { PathItem, Port, Position, RecordRow, Result } from './contract';
import { analysisStatusText, checkLabels, jsonBranches, keyCheck, keyCheckReason, knownAnalysisReasons, literalKey, outputId, outputLabel, pathDemandText, reviewBoundary, summarizePaths } from './taskSummary';
import type { Candidate, CheckState, Output } from './taskSummary';
import { readCandidateProof, type CandidateProof } from './candidateProof';
import { TwoStepEvidence } from './TwoStepEvidence';
import { UnionOutputEvidence } from './UnionOutputEvidence';
import { isJoinVisibilityUnverified, isUnverifiedUnionDerivation, physicalReadView } from './unverifiedUnion';
import './workbench.css';

const Editor = lazy(() => import('./SubfieldEditor'));
type Dialect = 'hive' | 'spark';
type Request = Parameters<typeof analyzeSubfieldSql>[0];
let localRequestSequence = 0;
type Excerpt = typeof archiveEvidence.r12;
const adhoc: EvidenceOrigin = { kind: 'AD_HOC' };
const constructed: EvidenceOrigin = { kind: 'CONSTRUCTED' };
function declaredExcerpt(item: Excerpt): EvidenceOrigin {
  return {
    kind: 'EXCERPT', manifest_ref: `${item.provenance_ref.path}#${item.provenance_ref.json_pointer} (SHA-256 ${item.provenance_ref.sha256})`,
    archive_sha256: item.archive_sha256, member: item.member, member_ordinal: item.member_ordinal,
    original_size: item.member_bytes, original_sha256: item.original_sha256,
    byte_range: { start: item.start_byte_inclusive, end: item.end_byte_exclusive },
    range_sha256: item.excerpt_sha256, encoding: 'utf-8', context: item.source_context,
  };
}
type Example = { name: string; sql: string; dialect: string; note: string; excerpt?: Excerpt; context?: string };
const reducedArchiveContext = '合成精简查询 · 仅定位提交 SQL';
const examples: Example[] = [
  {name: '同表双 JSON 五级演示', sql: twoJsonSQL, dialect: 'spark', note: '合成示例：双 JSON 载体通过两级 CTE。'},
  {name: '单列五级演示', sql: layeredSQL, dialect: 'spark', note: '合成示例：单 JSON 载体通过两级 CTE。'},
  {name: '单表合成 SQL', sql: archive.sql, dialect: archive.parser_dialect,
    note: `${reducedArchiveContext}`, context: reducedArchiveContext},
  {name: '合成窗口摘录', sql: coupon.sql, dialect: coupon.dialect, excerpt: archiveEvidence.r12, note: '合成片段：展示窗口和行选择证据。'},
  {name: '单根双分支示例', dialect: 'spark', note: '构造示例：值分支不代表已验证行集。',
    sql: "WITH base AS (SELECT t.j FROM src t), l AS (SELECT get_json_object(x.j,'$.a') AS a FROM base x), r AS (SELECT get_json_object(x.j,'$.b') AS b FROM base x) SELECT COALESCE(l.a,r.b) AS protected FROM l CROSS JOIN r"},
  {name: '合成文本 Map 摘录', sql: archiveEvidence.r24.sql, dialect: archiveEvidence.r24.dialect,
    excerpt: archiveEvidence.r24, note: '合成 HQL 片段：分别定位函数及查键。'},
];
type ReadTarget = NonNullable<ReturnType<typeof preferredJsonReadLocation>>;
type Check = { status: CheckState; path: string; ports: Output[]; message: string; candidate?: Candidate; proof?: CandidateProof | null };
const checkCopy: Record<CheckState, string> = {
  observed: '在本次 SQL 中找到与此键重叠的读取；此结论不能证明每个所选输出都依赖此键。',
  'not-observed': '在本次 SQL 和所列输出范围下未见与此键重叠的读取。键是否存在、修改是否有影响仍需核对。',
  unknown: '服务没有提供可确认的逐键结果。请核对源字段、输出范围和未决记录。',
};
function PathChip({ state }: { state: CheckState }) {
  return <span className="j-path-chip" data-status={state}>{checkLabels[state]}</span>;
}
const roleNames: Record<string, string> = { VALUE: '输出值依赖', CONDITION: '条件依赖', CARRIER: '载体传递', STRUCTURE: '结构依赖', RELATIONAL: '关系依赖', REPRESENTATION: '原始表示依赖' };
const pathLabel = ({ input }: PathItem) => `${input.source} · ${input.column} · ${input.path}`;

interface Branch { label: string; children: Map<string, Branch>; paths: PathItem[] }
const branch = (label: string): Branch => ({ label, children: new Map(), paths: [] });
function tokenLabel({ kind, value }: NonNullable<PathItem['input']['path_tokens']>[number]) {
  if (kind === 'key') return value === '' ? '空键（""）' : String(value ?? '键名未提供');
  if (kind === 'index') return `[${value ?? '?'}]`;
  if (kind === 'any_element') return '[*]';
  if (kind === 'decode') return '解码';
  if (kind === 'parse') return '解析';
  return value === undefined ? kind : `${kind}：${value}`;
}
function treeOf(paths: PathItem[]) {
  const root = branch('');
  for (const item of paths) {
    const { source, column, path_tokens: tokens } = item.input;
    const segments = [
      [source, source], [column, column],
      ...(tokens ?? []).map(token => [JSON.stringify([token.kind, token.value]), tokenLabel(token)]),
    ];
    let parent = root;
    for (const [key, label] of segments) {
      if (!parent.children.has(key)) parent.children.set(key, branch(label));
      parent = parent.children.get(key)!;
    }
    parent.paths.push(item);
  }
  return root;
}
function contains(node: Branch, id?: string): boolean {
  return node.paths.some(item => item.id === id) || [...node.children.values()].some(child => contains(child, id));
}
const PathTree = memo(function PathTree({ root, active, select, byPath, check }: {
  root: Branch; active?: string; select: (item: PathItem) => void; byPath: Map<string, Output[]>; check: Check | null;
}) {
  function pathButton(item: PathItem) {
    return <button type="button" className="json-tree-row" key={item.id}
      aria-pressed={item.id === active} onClick={() => select(item)}>
      <span>{item.input.path === '$' ? '整列（$）' : item.input.path}</span>
      {item.input.path !== '$' && <><PathChip state={item.uses.length > 0 ? 'observed' : 'unknown'} />
        <span className="j-path-destination">{byPath.get(item.id)?.slice(0, 2).map(output => output.output ?? '未命名输出').join('、') || '下游输出暂不能判断'}
          {(byPath.get(item.id)?.length ?? 0) > 2 && ` 等 ${byPath.get(item.id)?.length} 个输出`}</span></>}
    </button>;
  }
  function render([key, node]: [string, Branch], depth: number) {
    if (depth >= 2 && !node.children.size && node.paths.length === 1) return pathButton(node.paths[0]);
    return <details key={key} open={depth < 5 || contains(node, active) || undefined}><summary>{node.label}</summary>
      <div className="json-tree-children">
        {node.paths.map(pathButton)}
        {[...node.children.entries()].map(child => render(child, depth + 1))}
      </div>
    </details>;
  }
  return <section className="json-tree-pane" aria-label="JSON 枝干树">
    <div className="json-pane-head"><h2>JSON 枝干树</h2><p>显示本次分析发现的路径；不是完整 JSON 结构。</p></div>
    {check?.candidate && <p className="j-path-destination" aria-label="按所选范围检查的键">
      {check.candidate.source} · {check.candidate.column} · {check.path} <PathChip state={check.status} />
    </p>}
    {root.children.size ? [...root.children.entries()].map(child => render(child, 0)) : <p className="muted">没有已绑定的源路径。</p>}
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
  return path ? [{ label: row.producer ? '载体' : '读取调用', position: row.position }, { label: 'JSON 路径字面量', position: path }]
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
  const fileInput = useRef<HTMLInputElement>(null);
  const fileSelection = useRef(0);
  const [pendingSqlFile, setPendingSqlFile] = useState<{ name: string; text: string } | null>(null);
  const [sqlFileStatus, setSqlFileStatus] = useState('');
  const [longSqlFile, setLongSqlFile] = useState<LocalSqlFile | null>(null);
  const [sql, setSql] = useState(''), [dialect, setDialect] = useState<Dialect>('spark');
  const [schemas, setSchemas] = useState(''), [example, setExample] = useState<Example | null>(null);
  const [editorOpen, setEditorOpen] = useState(false), [location, setLocation] = useState<Position | null>(null);
  const [result, setResult] = useState<Result | null>(null), [submitted, setSubmitted] = useState('');
  const [positionIndex, setPositionIndex] = useState<SQLPositionIndex | null>(null);
  const [surface, setSurface] = useState<'table' | 'json'>('table');
  const [selected, setSelected] = useState<PathItem | null>(null), [query, setQuery] = useState('');
  const [picked, setPicked] = useState<{ title: string; rows: RecordRow[]; fromReview: boolean; receiptTarget?: ReadTarget } | null>(null);
  const [protectedSlots, setProtectedSlots] = useState<number[]>([]);
  const [candidatePath, setCandidatePath] = useState(''), [candidateSource, setCandidateSource] = useState(''), [candidateColumn, setCandidateColumn] = useState('');
  const [inputMode, setInputMode] = useState<'path' | 'key'>('path');
  const analysisArea = useRef<HTMLDivElement>(null), [sqlSplit, setSqlSplit] = useState(44);
  const [check, setCheck] = useState<Check | null>(null);
  const receiptLocation = useRef(false);
  const twoStepLocation = useRef(false);
  const [twoStepOutputId, setTwoStepOutputId] = useState('');
  const twoStepEnabled = import.meta.env.VITE_SUBFIELD_TWO_STEP_EVIDENCE === '1';
  const clearTwoStepLocation = useCallback(() => {
    if (twoStepLocation.current) { twoStepLocation.current = false; setLocation(null); }
  }, []);
  const [review, setReview] = useState<unknown>(null), [reviewStatus, setReviewStatus] = useState('尚未执行高级核查。');
  const [pathProof, setPathProof] = useState<string | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const pending = useRef(false);
  const revision = useRef(0);
  const [analysisSnapshot, setAnalysisSnapshot] = useState<EvidenceSnapshot | null>(null);
  const [reviewSnapshot, setReviewSnapshot] = useState<EvidenceSnapshot | null>(null);
  const [downloadError, setDownloadError] = useState('');
  const [downloading, setDownloading] = useState(false);
  const writing = useRef<number | null>(null);
  const inspectorEvidence = useRef<HTMLDivElement>(null);
  const physical = useMemo(() => result ? physicalReadView(result) : null, [result]);
  const joinDiagnostics = result?.uses.filter(isJoinVisibilityUnverified) ?? [];
  const unionDiagnostics = result?.uses.filter(isUnverifiedUnionDerivation) ?? [];
  const paths = useMemo(() => pathTree(physical), [physical]);
  const roots: Output[] = useMemo(() => rootOutputs(result?.mappings ?? []), [result]);
  const twoStepOutputs = useMemo(() => {
    const choices = new Map<string, { output: Output; mapping: RecordRow }>();
    if (!twoStepEnabled || !result) return choices;
    const mappings = new Map<string, RecordRow | null>();
    for (const row of result.mappings) {
      const { statement, scope, slot } = row;
      if (typeof statement !== 'number' || typeof scope !== 'string' || typeof slot !== 'number') continue;
      const id = outputId({ statement, scope, slot });
      mappings.set(id, mappings.has(id) ? null : row);
    }
    for (const output of roots) {
      const id = outputId(output), mapping = mappings.get(id);
      if (mapping) choices.set(id, { output, mapping });
    }
    return choices;
  }, [twoStepEnabled, result, roots]);
  const twoStepOutput = twoStepOutputs.get(twoStepOutputId);
  const task = useMemo(() => summarizePaths(physical, paths), [physical, paths]);
  const tree = useMemo(() => treeOf(paths.filter(item => item.input.path === '$').concat(task.branches)), [paths, task]);
  const sourceColumns = useMemo(() => [...new Map(paths.map(({ input }) => [JSON.stringify([input.source, input.column]), input])).values()], [paths]);
  const selectedOutputs = roots.filter((_, index) => protectedSlots.includes(index));
  const allSelected = roots.length > 0 && selectedOutputs.length === roots.length;
  const scopeText = !roots.length ? '没有可选输出' : allSelected ? `全部 ${roots.length} 个输出（默认）`
    : selectedOutputs.length ? `已选 ${selectedOutputs.length} / ${roots.length} 个输出（自定义）`
      : `尚未选择输出（0 / ${roots.length}）`;
  const scopeNotice = !roots.length ? '当前 SQL 没有可检查的输出，请核对分析结果。'
    : !selectedOutputs.length ? '请选择本次问题需要检查的输出。未选择输出时不会检查。' : '';
  const scopeDetails = useRef<HTMLDetailsElement>(null);
  const [rangeChanged, setRangeChanged] = useState(false);
  const [keyChecking, setKeyChecking] = useState(false);
  const projection = useMemo(() => selected && physical ? projectPath(physical, selected) : null, [selected, physical]);
  // Choose from the original response: projecting a path can remove port reads.
  const buildGraph = result?.mappings.some(row => row.terminal_binding || row.port_reads)
    ? layeredGraphFacts : graphFacts;
  const fullGraph = useMemo(() => physical ? buildGraph(physical) : null, [physical, buildGraph]);
  const focusedGraph = useMemo(() => projection ? buildGraph(projection) : null, [projection, buildGraph]);
  const hits = useMemo(() => query.trim() ? paths.filter(path => pathLabel(path).toLowerCase().includes(query.trim().toLowerCase())).slice(0, 12) : [], [paths, query]);
  const onPick = useCallback((title: string, rows: RecordRow[], fromReview = false) => setPicked({ title, rows, fromReview }), []);
  const onReportPick = useCallback((title: string, rows: RecordRow[], fromReview = false) => {
    onPick(title, rows, fromReview);
    requestAnimationFrame(() => {
      inspectorEvidence.current?.scrollIntoView({ block: 'start' });
      inspectorEvidence.current?.focus({ preventScroll: true });
    });
  }, [onPick]);
  const onReviewPick = useCallback((title: string, rows: RecordRow[]) => onReportPick(title, rows, true), [onReportPick]);
  const select = useCallback((path: PathItem) => {
    setSelected(path); setPicked(null); setSurface('json'); setQuery('');
  }, []);
  function clearSqlFileSelection() {
    fileSelection.current++;
    setPendingSqlFile(null);
    setSqlFileStatus('');
  }
  function reset() {
    clearSqlFileSelection();
    revision.current++;
    receiptLocation.current = false;
    twoStepLocation.current = false; setTwoStepOutputId('');
    setPositionIndex(null); setPathProof(null);
    setAnalysisSnapshot(null); setReviewSnapshot(null); setDownloadError(''); setDownloading(false);
    setResult(null); setSurface('table'); setSelected(null); setPicked(null); setQuery(''); setError('');
    setProtectedSlots([]); setRangeChanged(false); setKeyChecking(false); setReview(null); setReviewStatus('尚未执行高级核查。'); setCheck(null); setCandidatePath(''); setCandidateSource(''); setCandidateColumn(''); setLocation(null);
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
      const origin: EvidenceOrigin = selectedExample?.sql === input ? (selectedExample.excerpt
        ? declaredExcerpt(selectedExample.excerpt)
        : selectedExample.context ? { kind: 'CONSTRUCTED', context: selectedExample.context } : constructed) : adhoc;
      const captured = await requestSnapshot(request, origin);
      if (issued !== revision.current) return;
      const response = normalize(captured.rawResponse);
      setPositionIndex(createSQLPositionIndex(input));
      setAnalysisSnapshot(captured);
      setSubmitted(input); setResult(response); setEditorOpen(false);
      setProtectedSlots(rootOutputs(response.mappings).map((_, index) => index));
      const branches = jsonBranches(pathTree(physicalReadView(response)));
      const first = branches.find(item => item.uses.length > 0) ?? branches[0];
      if (first) {
        select(first);
        setCandidateSource(first.input.source); setCandidateColumn(first.input.column);
      }
    } catch (exception) { if (issued === revision.current) setError(exception instanceof Error ? exception.message : '分析失败'); }
    finally { pending.current = false; setBusy(false); }
  }
  function replaceSqlDraft(value: string) {
    reset(); setExample(null); setSql(value);
  }
  function loadSqlFile(file: { name: string; text: string }) {
    replaceSqlDraft(file.text);
    setEditorOpen(true);
    setSqlFileStatus(`已打开「${file.name}」。确认内容后点「分析 SQL」。`);
  }
  async function chooseSqlFile(file: File) {
    clearSqlFileSelection();
    const selection = fileSelection.current;
    setSqlFileStatus(`正在读取「${file.name}」…`);
    try {
      const local = await readSqlFile(file);
      if (selection !== fileSelection.current) return;
      if (local.long) {
        setSqlFileStatus('');
        setLongSqlFile(local);
      } else if (sql.length > 0) {
        setSqlFileStatus('');
        setPendingSqlFile(local);
      } else {
        loadSqlFile(local);
      }
    } catch (error) {
      if (selection === fileSelection.current) setSqlFileStatus(error instanceof Error ? error.message : '无法读取所选 SQL 文件。');
    }
  }
  function loadExample(example: Example, run = false) {
    const mode = example.dialect === 'hive' ? 'hive' : 'spark';
    reset(); setSql(example.sql); setDialect(mode); setSchemas(''); setExample(example);
    if (run) void analyze(example.sql, mode, '', example);
  }
  function invalidateReview() {
    revision.current++;
    setReview(null); setReviewSnapshot(null); setCheck(null); setPathProof(null); setDownloadError(''); setDownloading(false);
    setPicked(value => value?.fromReview ? null : value);
    setReviewStatus('尚未执行高级核查。');
    if (receiptLocation.current) { receiptLocation.current = false; setLocation(null); }
  }
  function updateScope(next: number[]) {
    if (next.length === protectedSlots.length && next.every(slot => protectedSlots.includes(slot))) return;
    setProtectedSlots(next);
    invalidateReview();
    setRangeChanged(true);
    setReviewStatus('检查范围已更新，请重新检查。');
  }
  async function runReview(candidate?: Candidate, displayPath = candidatePath.trim()) {
    if (pending.current || !analysisSnapshot) return;
    if (!selectedOutputs.length) { setReviewStatus('请选择至少一个根输出。'); return; }
    const assessment = candidate && { path: displayPath, ports: selectedOutputs, candidate };
    pending.current = true; setBusy(true); invalidateReview(); setReviewStatus('正在评审…');
    if (candidate) { setKeyChecking(true); setRangeChanged(false); }
    const issued = revision.current;
    try {
      const ports: Port[] = selectedOutputs.map(({ statement, scope, slot }) => ({ statement, scope, slot }));
      const request: Request = { ...analysisSnapshot.request, protected_outputs: ports,
        ...(candidate ? { candidate_keys: [{ source: candidate.source, column: candidate.column, keys: [candidate.key] }] } : {}) };
      const captured = await requestSnapshot(request, analysisSnapshot.origin);
      if (issued !== revision.current) return;
      const response = normalize(captured.rawResponse);
      const proof = candidate ? await readCandidateProof(analysisSnapshot, captured, candidate, positionIndex) : null;
      if (issued !== revision.current) return;
      const hasReview = response.review !== null && typeof response.review === 'object' && !Array.isArray(response.review);
      if (hasReview) setReviewSnapshot(captured);
      setReview(hasReview ? response.review : null);
      setPathProof(pathDemandText(response.review));
      if (assessment && candidate) {
        const status = keyCheck(response.review, candidate);
        const reason = status === 'unknown' ? keyCheckReason(response.review, assessment.ports, candidate) : undefined;
        setCheck({ ...assessment, status, message: reason || checkCopy[status], proof });
      }
      setReviewStatus(hasReview ? (candidate ? '服务键检查记录' : '服务评审记录') : '该次响应未提供评审；可下载本次分析证据。');
    } catch (exception) {
      if (issued === revision.current) {
        setPathProof(pathDemandText(null));
        setReviewStatus(`未取得评审包；可下载本次分析证据。${exception instanceof Error ? exception.message : ''}`);
        if (assessment) setCheck({ ...assessment, status: 'unknown', message: '检查请求未完成，请重试。' });
      }
    }
    finally { pending.current = false; setBusy(false); setKeyChecking(false); }
  }
  function runKeyCheck(explicitEmpty = false) {
    if (pending.current) return;
    if (!selectedOutputs.length) return;
    const path = explicitEmpty ? '' : candidatePath;
    const source = candidateSource.trim(), column = candidateColumn.trim();
    const key = inputMode === 'path' ? literalKey(path) : path === '' && !explicitEmpty ? null : path;
    const label = inputMode === 'key' ? (key === '' ? '空键（""）' : key !== null ? JSON.stringify(key) : '') : path.trim();
    const message = !source || !column ? '请填写源表和 JSON 列。'
      : key === null ? (inputMode === 'path'
        ? '路径方式只支持字面顶层键，例如 user_id 或 $.user_id。检查带点号的顶层键，请切换到字面键名。'
        : '请填写顶层键名；如需检查空字符串，请使用“检查空键”。')
      : Array.from(key).length > 256 ? '每个键最多 256 个字符。'
      : '';
    if (message || key === null) {
      invalidateReview(); setCheck({ status: 'unknown', path: label, ports: selectedOutputs, message }); return;
    }
    void runReview({ source, column, key }, label);
  }
  const downloadSnapshot = reviewSnapshot ?? analysisSnapshot;
  const downloadKey = reviewSnapshot?.request.candidate_keys?.[0];
  async function downloadEvidence() {
    const issued = revision.current;
    // A hash from an invalidated revision may still be running.
    if (!downloadSnapshot || pending.current || writing.current === issued) return;
    writing.current = issued; setDownloading(true); setDownloadError('');
    try {
      const { buildEvidenceBundle } = await import('./evidenceBundle');
      const bundle = await buildEvidenceBundle(downloadSnapshot);
      if (issued !== revision.current) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2) + '\n'], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `subfield-${downloadKey ? 'key-check' : reviewSnapshot ? 'review' : 'analysis'}-${downloadSnapshot.requestId}.json`;
      document.body.append(link);
      try { link.click(); }
      finally { link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); }
    } catch (exception) {
      if (issued === revision.current) setDownloadError(exception instanceof Error ? exception.message : '证据下载失败。');
    } finally {
      if (writing.current === issued) writing.current = null;
      if (issued === revision.current) setDownloading(false);
    }
  }
  const evidence = useMemo(() => picked ?? (selected && projection ? { title: pathLabel(selected), rows: [
    ...selected.uses, ...projection.mappings.flatMap(row => [row, ...(Array.isArray(row.port_reads) ? row.port_reads : [])]),
  ] } : null), [picked, selected, projection]);
  const unionSelectedOutput = picked?.rows.length === 1 && (physical?.mappings.includes(picked.rows[0]) || projection?.mappings.includes(picked.rows[0])) &&
    typeof picked.rows[0].statement === 'number' && typeof picked.rows[0].scope === 'string' && typeof picked.rows[0].slot === 'number'
    ? outputId({ statement: picked.rows[0].statement, scope: picked.rows[0].scope, slot: picked.rows[0].slot }) : null;
  const selectedOutputsForPath = selected ? task.byPath.get(selected.id) ?? [] : [];
  const readLocation = picked?.receiptTarget ?? preferredJsonReadLocation(selected?.uses ?? [], positionIndex);
  const checkedCandidate = check?.candidate;
  const matchingReads = checkedCandidate ? task.branches.flatMap(path => {
    const { source, column, key } = checkedCandidate;
    const top = path.input.path_tokens?.[0];
    return path.input.source === source && path.input.column === column && top?.kind === 'key' && top.value === key
      ? path.uses.filter(row => row.kind === 'EXTRACT' && row.role !== 'REPRESENTATION').map(row => ({ path, row }))
      : [];
  }) : [];
  const readSites = new Set<string>();
  const receiptReads = matchingReads.flatMap(({ path, row }) => {
    const target = preferredJsonReadLocation([row], positionIndex);
    if (!target) return [];
    const id = JSON.stringify([path.id, target.position.start, target.position.end]);
    if (readSites.has(id)) return [];
    readSites.add(id);
    return [{ id, path, row, ...target }];
  });
  const locateEvidence = (range: Position, fromReceipt = false) => {
    if (!analysisSnapshot || sql !== submitted || !positionIndex?.valid(range)) return;
    twoStepLocation.current = false;
    receiptLocation.current = fromReceipt;
    setLocation({ ...range });
    setEditorOpen(true);
  };
  function locateCandidateProof(position?: Position | null) {
    if (position) locateEvidence(position, true);
  }
  function openReceiptRead({ path, row, kind, position }: (typeof receiptReads)[number]) {
    select(path);
    setPicked({ title: pathLabel(path), rows: [row], fromReview: true, receiptTarget: { kind, position } });
    locateEvidence(position, true);
  }
  const declared = analysisSnapshot?.origin.kind === 'EXCERPT';
  const previewEvidence = (title: string, rows: RecordRow[]) =>
    <Evidence key={title} rows={rows} index={positionIndex} declared={declared} locate={locateEvidence} />;
  const editor = editorOpen && <div id="repository-sql-editor"><Suspense fallback={<p role="status">正在加载 SQL 编辑器…</p>}>
    <Editor sql={sql} dialect={dialect} busy={busy} locate={location} positionIndex={positionIndex} run={() => void analyze()}
      setSql={value => { if (value !== sql) replaceSqlDraft(value); }} />
  </Suspense></div>;
  const status = result?.coverage?.partial ? '部分恢复' : result?.coverage?.parsed === false ? '解析失败'
    : result?.coverage?.parsed === true ? '完整解析' : '解析状态未提供';
  const reasons = result ? knownAnalysisReasons(result) : [];
  const unknownCount = result?.unknowns?.length;
  const failedStatements = result?.unknowns?.filter(row => row.code === 'PARSE_ERROR') ?? [];
  const scope = declared && example?.excerpt
    ? `合成摘录 · #${example.excerpt.member_ordinal} · 原件第 ${example.excerpt.source_lines_inclusive.join('–')} 行（清单声明） · 仅分析此片段，非整件`
    : analysisSnapshot?.origin.kind === 'CONSTRUCTED' ? analysisSnapshot.origin.context ?? '构造示例 · 仅分析本次提交 SQL'
      : '手动提交 SQL · 本次提交全文';
  if (longSqlFile) return <LongSqlExcerpt file={longSqlFile} initialDialect={dialect} close={() => setLongSqlFile(null)} />;
  return <div className="subfield-app">
    <section className="subfield-main" aria-label="JSON 血缘工作台">
      <form id="analysis" onSubmit={event => { event.preventDefault(); void analyze(); }}>
        <div className="analysis-toolbar">
          <div className="actions analysis-primary">
            <button className="btn-primary" type="submit" disabled={busy}>分析 SQL</button>
            <button className="btn" type="button" aria-expanded={editorOpen} onClick={() => setEditorOpen(open => !open)}>编辑 SQL 原文</button>
            <button className="btn" type="button" disabled={busy} onClick={() => fileInput.current?.click()}>打开 SQL 文件</button>
            <small className="muted">本机文件预览上限 {sqlPreviewLimitLabel}</small>
            <input hidden ref={fileInput} type="file" aria-label="选择 SQL 文件" accept=".sql" disabled={busy}
              onChange={event => {
                const file = event.currentTarget.files?.[0];
                event.currentTarget.value = '';
                if (file) void chooseSqlFile(file);
              }} />
            <button className="btn" type="button" disabled={busy} onClick={() => loadExample(examples[0], true)}>试用示例</button>
            <label className="analysis-field">方言 <select className="select" value={dialect} disabled={busy} onChange={event => { reset(); setDialect(event.target.value as Dialect); }}>
            <option value="spark">Spark</option><option value="hive">Hive</option>
            </select></label>
          </div>
          <details className="analysis-options">
            <summary>示例与分析选项{schemas.trim() ? ' · 已填写源列清单' : ''}</summary>
            <div className="analysis-options-body">
              <p className="muted">两步读取证据：本机试用（{twoStepEnabled ? '已启用' : '未启用'}）
                {!twoStepEnabled && '。请按本机启动说明启用后重新打开页面。'}</p>
              <label className="analysis-field">加载示例 <select className="select" disabled={busy} value="" onChange={event => loadExample(examples[Number(event.target.value)])}>
                <option value="" disabled>选择示例</option>{examples.map((example, i) => <option key={example.name} value={i}>{example.name}</option>)}
              </select></label>
              {example && <p className="muted">{example.note}</p>}
              <details className="schema-options"><summary>源列清单（可选）</summary>
                <p className="muted">由调用方声明，未经生产数据目录核验。</p>
                <textarea aria-label="源列清单 JSON" value={schemas} disabled={busy} onChange={event => { reset(); setSchemas(event.target.value); }} />
              </details>
            </div>
          </details>
        </div>
        {sqlFileStatus && <p role="status" className="j-scope">{sqlFileStatus}</p>}
        {pendingSqlFile && <div className="actions">
          <p role="status">已选「{pendingSqlFile.name}」。打开会替换当前 SQL 草稿；尚未分析。</p>
          <button type="button" className="btn" disabled={busy} onClick={() => loadSqlFile(pendingSqlFile)}>替换当前 SQL 草稿</button>
          <button type="button" className="btn" onClick={clearSqlFileSelection}>取消打开</button>
        </div>}
        {error && <p id="error" role="alert">{error}</p>}
      </form>
      {result && <section className="j-task-summary" aria-labelledby="j-task-heading" aria-busy={busy}>
        <h2 id="j-task-heading" className="j-task-heading">本次核查结论</h2>
        <p role="status">{analysisStatusText(result, task.observed.length > 0)}</p>
        {pathProof && <p role="status">所选输出：{pathProof}</p>}
        {unionDiagnostics.length > 0 && <p className="j-scope">集合类型转换未核验：{unionDiagnostics.length} 条路径诊断不计为物理读取。</p>}
        {reasons.length > 0 && <p className="j-scope">已知限制：{reasons.join('；')}。</p>}
        {task.observed.length > 0 && <p className="j-scope">已有证据：<strong>{task.observed.length} 条 JSON 路径</strong>
          {task.outputs.length > 0 && <> · 路径概览关联 <strong>{task.outputs.length} 个不同的下游输出</strong></>}。</p>}
        {result.coverage?.partial && <p className="j-scope">本次只分析了可恢复的语句。</p>}
        <p className="j-scope"><strong>SQL 分析待确认项：{unknownCount ?? '未提供'}</strong> · 仅统计本次 SQL 的静态解析与绑定记录</p>
        {task.observed.length > 0 && <p className="j-path-destination">例如：{task.observed.slice(0, 3).map(pathLabel).join('；')}
          {task.outputs.length > 0 && ` → 路径关联输出：${task.outputs.slice(0, 3).map(output => output.output ?? '未命名输出').join('、')}`}
          {task.outputs.length > 0 && task.observed.some(item => !task.byPath.has(item.id)) && '。部分读取的下游暂不能判断。'}</p>}
        <p className="j-scope">{scope} · {reviewBoundary}</p>
        <form className="j-path-check" onSubmit={event => { event.preventDefault(); runKeyCheck(); }}>
          <label>源表 <input list="j-source-tables" value={candidateSource} disabled={busy} onChange={event => {
            setCandidateSource(event.target.value); setCandidateColumn(''); invalidateReview();
          }} /></label>
          <datalist id="j-source-tables">{[...new Set(sourceColumns.map(item => item.source))].map(source => <option key={source} value={source} />)}</datalist>
          <label>JSON 列 <input list="j-source-columns" value={candidateColumn} disabled={busy} onChange={event => {
            setCandidateColumn(event.target.value); invalidateReview();
          }} /></label>
          <datalist id="j-source-columns">{sourceColumns.filter(item => item.source === candidateSource).map(item => <option key={item.column} value={item.column} />)}</datalist>
          <label>{inputMode === 'path' ? 'JSON 路径' : 'JSON 顶层键名'} <input id="j-candidate-path" value={candidatePath}
            placeholder={inputMode === 'path' ? '例如 $.user_id' : '例如 a.b'} disabled={busy} onChange={event => {
            setCandidatePath(event.target.value); invalidateReview();
          }} /></label>
          <button className="btn-primary" type="submit" disabled={busy || !selectedOutputs.length}>检查键</button>
        </form>
        <p className="j-scope j-key-mode"><button className="btn" type="button" disabled={busy} onClick={() => {
          setInputMode(inputMode === 'path' ? 'key' : 'path'); invalidateReview();
        }}>{inputMode === 'path' ? '按字面键名' : '按 JSON 路径'}</button>
          {inputMode === 'path' ? '支持 $.user_id 这样的顶层路径。' : '按原样检查；a.b 与 $.a 都是完整键名。'}
          {inputMode === 'key' && <button className="btn" type="button" disabled={busy || !selectedOutputs.length} onClick={() => runKeyCheck(true)}>检查空键</button>}
        </p>
        <details className="j-advanced-review" ref={scopeDetails}><summary>检查范围：{scopeText}</summary>
          {roots.length > 0 && <fieldset disabled={busy}><legend>手动选择检查输出</legend>
            <p className="j-scope">默认检查当前 SQL 的全部可选输出。只取消本次问题确实不涉及的输出；缩小范围后的结果仅适用于所选输出。</p>
            <div className="j-output-options">
              <label><input type="checkbox" checked={allSelected} ref={node => {
                if (node) node.indeterminate = !allSelected && selectedOutputs.length > 0;
              }} onChange={event => updateScope(event.target.checked ? roots.map((_, i) => i) : [])} /> 全选</label>
              {roots.map((output, i) => <label key={outputId(output)}><input type="checkbox" checked={protectedSlots.includes(i)} onChange={event => {
                updateScope(event.target.checked ? [...protectedSlots, i] : protectedSlots.filter(slot => slot !== i));
              }} /> {outputLabel(output)}</label>)}
            </div>
            {!allSelected && <button type="button" className="btn" onClick={() => updateScope(roots.map((_, i) => i))}>恢复全部输出</button>}
          </fieldset>}
        </details>
        {scopeNotice && <p className="j-scope">{scopeNotice}</p>}
        {!check && <p role="status" className="j-scope">{keyChecking ? '键检查：检查中' : rangeChanged
          ? '键检查：范围已改变，请重新检查。此前结果已失效。' : '键检查：尚未检查'}</p>}
        {check && <section className="j-path-result" aria-label="键检查回执">
          <div role="status">键检查：<PathChip state={check.status} /> <strong>{check.candidate && `${check.candidate.source} · ${check.candidate.column} · `}{check.path || '未输入路径'}</strong> · {check.message}</div>
          {check.status === 'not-observed' && <p className="j-scope">此键可作为待核查的剪枝候选。键是否存在、行集与修改影响仍需验证。</p>}
          {check.proof && check.candidate && <ul className="j-scope">
            <li>{`输出 ${outputLabel(check.ports[0])} 的 SELECT 读取了 ${check.proof.path}，与键 ${JSON.stringify(check.candidate.key)} 重叠。`}
              {check.proof.valuePosition && <button type="button" className="btn"
                onClick={() => locateCandidateProof(check.proof?.valuePosition)}>定位 SELECT 读取函数</button>}
            </li>
            <li>{`WHERE 使用 ${check.proof.filterColumn} 过滤行。行集未验证，不提供删除授权。`}
              {check.proof.predicate && <button type="button" className="btn"
                onClick={() => locateCandidateProof(check.proof?.predicate)}>定位 WHERE 谓词</button>}
            </li>
          </ul>}
          <p className="j-scope">本次检查范围：{allSelected ? `全部 ${check.ports.length} 个输出 · ` : ''}{check.ports.map(outputLabel).join('、')}</p>
          {check.candidate && <>
            {!receiptReads.length ? <p className="j-scope">本次没有可定位的读取证据：{matchingReads.length
              ? '匹配的读取记录没有有效的 SQL 位置。' : '当前 SQL 分析没有提供此源表、列和顶层键的匹配读取记录。'}
              {surface === 'json' && selected && ' 右侧分支可单独浏览。'}</p> : <>
              {picked ? (picked.receiptTarget
                ? null : <p className="j-scope">右侧当前显示其他证据，请从回执打开此键的读取证据。</p>)
                : selected && surface === 'json' && !receiptReads.some(item => item.path.id === selected.id) &&
                  <p className="j-scope">右侧当前显示其他分支，请从回执打开此键的读取证据。</p>}
              {receiptReads.length === 1
                ? <div className="actions"><button type="button" className="btn" onClick={() => openReceiptRead(receiptReads[0])}>
                  查看此键的读取证据</button></div>
                : <><p className="j-scope">请选择与此键重叠的具体读取位置：</p>
                  <div className="actions">{receiptReads.map(item => {
                    // Path-level mappings do not identify which read occurrence feeds a root slot.
                    const clause = typeof item.row.clause === 'string' ? item.row.clause : null;
                    const role = item.row.role ? roleNames[item.row.role] : null;
                    const sourcePosition = positionIndex?.editorPosition(item.position.start);
                    return <button type="button" className="btn" key={item.id} onClick={() => openReceiptRead(item)}>
                      {pathLabel(item.path)}{clause && ` · ${clause}`}{role && ` · ${role}`} · SQL 第 {sourcePosition?.lineNumber} 行第 {sourcePosition?.column} 列
                      （{item.kind === 'literal' ? '路径' : '调用'}） · 输出流向待确认</button>;
                  })}</div></>}
            </>}
          </>}
          {check.status === 'unknown' && check.candidate && <>
            {unknownCount === 0 && <p className="j-scope">SQL 分析待确认项为 0，仅表示本次分析没有报告待确认项；不代表键检查通过。行集、键是否存在及修改影响仍未验证。</p>}
            <div className="actions">
              <button type="button" className="btn" onClick={() => {
                if (scopeDetails.current) { scopeDetails.current.open = true; scopeDetails.current.querySelector('summary')?.focus(); }
              }}>查看检查范围</button>
            </div>
            <p className="j-scope">请保留本次问题需要检查的全部输出；若该范围暂不能判断，请补充证据。调整范围会改变问题，不能替代原范围的结论。</p>
          </>}
        </section>}
        <p className="j-scope">下一步：检查想修改的键，或在下方选一条分支查看输出与 SQL 证据。</p>
      </section>}
      <div className="workbench shell">
        <div className="j-analysis-area" ref={analysisArea} style={{ '--j-sql-split': `${sqlSplit}%` } as CSSProperties}>
          {editor}
          {editorOpen && <Splitter split={sqlSplit} setSplit={setSqlSplit} measureRef={analysisArea} label="调整 SQL 和血缘画布的宽度" />}
        <section className="work" aria-label="血缘画布">
          <div className="subfield-canvas-toolbar">
            <span className="subfield-tool-title">血缘画布</span>
            <div className="seg canvas-mode">{(['table', 'json'] as const).map(mode =>
              <button type="button" key={mode} disabled={busy} aria-pressed={surface === mode} onClick={() => {
                const first = mode === 'json' && !selected && (paths.find(path => path.input.path !== '$') ?? paths[0]);
                if (first) select(first);
                else { setSurface(mode); setPicked(null); }
              }}>{mode === 'table' ? '表血缘' : 'JSON 排查'}</button>
            )}</div>
            <div className="subfield-search">
              <input id="canvas-search" type="search" aria-label="查找表、列或路径"
                disabled={!paths.length} placeholder={!result ? '请先分析 SQL' : paths.length ? '查找表、列或路径' : '没有可搜索的路径'} value={query}
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
          <div className={surface === 'json' ? 'graph-layout json-canvas' : 'graph-layout'}>
            {surface === 'json' && <PathTree root={tree} active={selected?.id} select={select} byPath={task.byPath} check={check} />}
            <div className="json-flow-pane">
              {surface === 'json' && <div id="json-flow-head" className="json-pane-head">
                <div>
                  <h2 id="json-focus-title" tabIndex={-1}>{selected?.input.path ?? '从路径树选择路径'}</h2>
                  {selected && <><p id="json-focus">{selected.input.source} · {selected.input.column}</p>
                    {selectedOutputsForPath.length ? <p className="j-path-destination">路径流向概览：{selectedOutputsForPath.map(output => <button type="button" className="btn" key={outputId(output)} onClick={() => {
                      const row = projection?.mappings.find(item => item.root === true && item.statement === output.statement && item.scope === output.scope && item.slot === output.slot);
                      const id = outputId(output);
                      setTwoStepOutputId(twoStepOutputs.has(id) ? id : '');
                      onReportPick(outputLabel(output), row ? [row] : []);
                    }}>{outputLabel(output)}</button>)}</p> : <p className="j-path-destination">下游输出暂不能判断。</p>}
                    {readLocation ? <button type="button" className="btn" onClick={() => locateEvidence(readLocation.position, !!picked?.receiptTarget)}>{readLocation.kind === 'literal' ? '定位读取证据' : '定位读取调用'}</button>
                      : <p className="muted">没有可靠的读取位置。</p>}
                  </>}
                </div>
                {selected && <button className="btn" id="clear-path" type="button" onClick={() => { setSelected(null); setPicked(null); }}>清除路径</button>}
              </div>}
              <ReactGraph key={surface + (selected?.id ?? '')} graph={surface === 'json' ? focusedGraph : fullGraph}
                emptyMessage={busy ? '正在分析 SQL…' : !result ? '分析 SQL 后查看血缘。'
                  : paths.length ? '选择路径后查看下游链路。' : '本次分析没有已绑定的源路径。'} onPick={onPick} />
            </div>
          </div>
          <p className="canvas-bottom">滚动查看全图 · 虚线表示未决 · 点节点或连线查看证据</p>
        </section>
        </div>
        <aside className="inspector" aria-label="血缘详情">
          <div className="ins-head"><h2>血缘详情</h2></div>
          <div className="ins-scroll">
            <div className="subfield-detail-body" ref={inspectorEvidence} tabIndex={-1}>
              {twoStepEnabled && analysisSnapshot && positionIndex && <section className="j-two-step" aria-labelledby="j-two-step-output">
                <h3 id="j-two-step-output">查看输出的两步读取</h3>
                <label className="j-two-step-picker">查看哪个输出的两步读取
                  <select className="select" value={twoStepOutputId} disabled={!twoStepOutputs.size}
                    onChange={event => setTwoStepOutputId(event.target.value)}>
                    <option value="">选择一个输出</option>
                    {[...twoStepOutputs].map(([id, { output }]) => <option key={id} value={id}>{outputLabel(output)}</option>)}
                  </select>
                </label>
                {twoStepOutputs.size < roots.length && <p className="muted">部分输出无法唯一识别，不能查看这些输出的两步读取。</p>}
                {!roots.length && <p className="muted">当前分析没有可选输出。</p>}
                {!twoStepOutput && <p className="muted">只选择本次查看的输出，不改变键检查范围。</p>}
                {twoStepOutput && <>
                  <p className="muted">当前只查看输出 {outputLabel(twoStepOutput.output)} 的两步读取；键检查范围和结论不变。</p>
                  <TwoStepEvidence key={twoStepOutputId} snapshot={analysisSnapshot} output={twoStepOutput.output}
                    mapping={twoStepOutput.mapping} index={positionIndex} clearLocation={clearTwoStepLocation}
                    locate={position => { locateEvidence(position); twoStepLocation.current = true; }} />
                  <p className="muted">当前下载包不包含本次两步详情响应。</p>
                </>}
              </section>}
              {evidence ? <><h3>{evidence.title}</h3>
                <Evidence key={evidence.title} rows={evidence.rows} index={positionIndex} declared={declared} locate={range => locateEvidence(range, !!picked?.receiptTarget)} /></> : <p className="muted">选择路径、节点或连线查看服务证据。</p>}
              {result && Array.isArray(result.union_output_reads) && result.union_output_reads.length > 0 && analysisSnapshot &&
                positionIndex && sql === submitted && <UnionOutputEvidence key={analysisSnapshot.requestId}
                  result={result} snapshot={analysisSnapshot} index={positionIndex} selectedOutput={unionSelectedOutput} locate={locateEvidence} />}
              {joinDiagnostics.length > 0 && <details>
                <summary>JOIN ON 来源未核验</summary>
                <section aria-label="JOIN ON 来源诊断">
                  <p>无法确认该读取引用的关系在当前 JOIN ON 中可见，不计为物理读取，也不证明输出流向。</p>
                  <ul>{joinDiagnostics.map((row, i) => {
                    const range = preferredJsonReadLocation([row], positionIndex);
                    return <li key={i}>
                      {typeof row.path === 'string' && <code>{row.path}</code>}
                      {range && <button type="button" className="btn" onClick={() => locateEvidence(range.position)}>
                        定位未证 JOIN ON {range.kind === 'literal' ? '路径字面量' : '调用'}
                      </button>}
                    </li>;
                  })}</ul>
                </section>
              </details>}
              {result && <Raw title="本次提交 SQL" value={submitted} />}
              {result && <details open={declared || undefined}><summary>其他分析记录</summary>
                <AnalysisReports result={physical ?? result} pick={onReportPick} preview={previewEvidence} />
                <Raw title="查看原始分析 JSON" value={result} />
              </details>}
            </div>
            {result && downloadSnapshot && <details className="evidence-download">
              <summary>分析来源与证据下载</summary>
              <div className="evidence-download-body">
                <p>{scope}{declared && <> · 原件坐标未核对</>}</p>
                {result.coverage?.partial && <div>
                  <p>已恢复语句：{result.coverage.recovered ?? '服务未提供'}</p>
                  {failedStatements.map((row, i) => <p key={i}>失败语句 {typeof row.statement === 'number' ? row.statement : '编号未提供'}：
                    {row.position && positionIndex?.valid(row.position) ? `提交 SQL 代码点 [${row.position.start}, ${row.position.end})` : '位置未记录'}</p>)}
                </div>}
                <button className="btn" type="button" disabled={busy || downloading} onClick={() => void downloadEvidence()}>
                  {downloading ? '正在准备证据…' : '下载证据（JSON）'}
                </button>
                <p>将下载：{reviewSnapshot ? <>{downloadKey
                  ? `键检查证据 · ${downloadKey.source} · ${downloadKey.column} · ${downloadKey.keys[0] === '' ? '空键（""）' : downloadKey.keys[0]} · 检查范围：`
                  : '剪枝评审证据 · 保护输出：'}{reviewSnapshot.request.protected_outputs?.map(port =>
                  `${port.statement}/${port.scope}/${port.slot}`).join('、')}</> : '分析证据'}。含提交 SQL，仅保存到本机。</p>
                {!reviewSnapshot && protectedSlots.length > 0 && <p className="muted">所选输出尚无当前评审包。</p>}
                {downloadError && <p role="alert">{downloadError}</p>}
              </div>
            </details>}
            {result && <details className="reports j-advanced-review">
              <summary>高级核查记录</summary>
              <button type="button" disabled={busy || !protectedSlots.length} onClick={() => void runReview()}>核查所选输出</button>
              <p role="status">{reviewStatus}</p>
              {review != null && <><p>仅限当前 SQL 和所选根输出；未证明裁剪安全。未列出的路径不能据此判定为可删。</p>
                <ReviewSummary value={review} pick={onReviewPick} preview={previewEvidence} />
                <Raw value={review} title="查看原始评审 JSON" /></>}
            </details>}
          </div>
        </aside>
      </div>
      <footer className="subfield-status">
        <span className={`pill ${busy ? 'running' : ''}`} role="status">{busy ? '处理中…' : result ? `服务结果 · ${physical?.uses.length ?? 0} 个使用点` : '等待分析'}</span>
        {result && <>
          <span>{declared ? '合成摘录 · 仅此片段' : analysisSnapshot?.origin.kind === 'CONSTRUCTED' ? '构造示例' : '手动提交'}</span>
          <span>{status}</span><span>{result.coverage?.complete === true ? '服务报告覆盖完整' : '覆盖未确认'}</span><span>SQL 分析待确认项 {unknownCount ?? '未提供'}</span>
        </>}
      </footer>
    </section>
  </div>;
}
