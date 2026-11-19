import { useEffect, useMemo, useRef, useState } from 'react';
import { analyzeSubfieldSql } from '../api/client';
import type { Position, Result } from './contract';
import { submittedSqlHash } from './evidenceBundle';
import { preferredJsonReadLocation } from './jsonReadLocation';
import { normalize } from './model.mjs';
import { maxSqlCharacters, type LocalSqlFile } from './sqlFile';
import { createSQLPositionIndex } from './sqlPositionIndex';
import { analysisStatusText } from './taskSummary';
import { isJoinVisibilityUnverified, isUnverifiedPhysicalRead, isUnverifiedUnionDerivation } from './unverifiedUnion';

type Dialect = 'spark' | 'hive';
const visibleText = (text: string) => text.replace(/\r\n?/g, '\n');
const countPoints = (text: string) => { let result = 0; for (const _char of text) result++; return result; };
function countThrough(sorted: number[], offset: number) {
  let lo = 0, hi = sorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (sorted[mid] <= offset) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}
const splitsSurrogate = (text: string, offset: number) => /[\uD800-\uDBFF][\uDC00-\uDFFF]/.test(text.slice(offset - 1, offset + 1));
type Selected = {
  sql: string; previewStart: number; previewEnd: number; lineFrom: number; lineTo: number;
  byteRange: Position; codePoints: Position;
};
type ExcerptResult = {
  selected: Selected; result: Result; dialect: Dialect; fileHash: string | null; excerptHash: string | null;
  location: 'file' | 'relative';
};

export function LongSqlExcerpt({ file, initialDialect, close }: { file: LocalSqlFile; initialDialect: Dialect; close: () => void }) {
  const { name, text, bom } = file;
  const preview = useRef<HTMLTextAreaElement>(null);
  const active = useRef(false);
  const [dialect, setDialect] = useState(initialDialect);
  const [selected, setSelected] = useState<Selected | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [result, setResult] = useState<ExcerptResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reveal, setReveal] = useState('');
  const { display, fileLocation } = useMemo(() => {
    const display = visibleText(text);
    const lineStarts = [0, ...Array.from(display.matchAll(/\n/g), match => match.index + 1)];
    return { display, fileLocation(offset: number) {
      const line = countThrough(lineStarts, offset);
      return { line, column: offset - lineStarts[line - 1] + 1 };
    } };
  }, [text]);
  const indexes = useMemo(() => {
    if (!result) return null;
    const sql = result.selected.sql;
    return { excerpt: createSQLPositionIndex(sql), collapsed: Array.from(sql.matchAll(/\r\n/g), match => match.index + 1) };
  }, [result]);
  const excerptIndex = indexes?.excerpt;

  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);

  function confirmSelection() {
    if (!preview.current) return;
    setSelected(null); setAcknowledged(false); setError(''); setReveal(''); setResult(null);
    const { selectionStart: start, selectionEnd: end } = preview.current;
    if (start >= end || splitsSurrogate(display, start) || splitsSurrogate(display, end)) {
      setError('请在原文件预览中选中连续文字，并确保两端都是完整字符。');
      return;
    }
    // Textarea uses LF and UTF-16; restore original CRLF or CR byte boundaries before slicing.
    let original = 0, visible = 0, originalStart = 0;
    while (visible < end) {
      if (visible === start) originalStart = original;
      original += text[original] === '\r' && text[original + 1] === '\n' ? 2 : 1;
      visible++;
    }
    const sql = text.slice(originalStart, original);
    const count = countPoints(sql);
    if (!sql.trim()) { setError('所选片段没有 SQL 文本。'); return; }
    if (count > maxSqlCharacters) { setError('所选片段超过 65,536 个 Unicode 码点；请缩小范围。'); return; }
    const before = text.slice(0, originalStart);
    const pointStart = countPoints(before);
    const byteStart = new TextEncoder().encode(before).length + (bom ? 3 : 0);
    setSelected({ sql, previewStart: start, previewEnd: end, lineFrom: fileLocation(start).line,
      lineTo: fileLocation(end - 1).line, byteRange: { start: byteStart, end: byteStart + new TextEncoder().encode(sql).length },
      codePoints: { start: pointStart, end: pointStart + count } });
  }

  async function run() {
    if (!selected || !acknowledged || busy || !preview.current) return;
    if (preview.current.selectionStart !== selected.previewStart || preview.current.selectionEnd !== selected.previewEnd) {
      setAcknowledged(false); setError('选区已改变，请重新确认所选片段。'); return;
    }
    setBusy(true); setResult(null); setError(''); setReveal('');
    try {
      const raw = normalize(await analyzeSubfieldSql({ sql: selected.sql, dialect }));
      const [fileHash, excerptHash] = await Promise.all([
        submittedSqlHash((bom ? '\uFEFF' : '') + text).catch(() => null),
        submittedSqlHash(selected.sql).catch(() => null),
      ]);
      if (!active.current) return;
      const returned = raw.coverage?.sql_sha256, returnedDialect = raw.coverage?.dialect;
      if ((returned !== undefined && excerptHash && returned !== excerptHash) ||
          (returnedDialect !== undefined && returnedDialect !== dialect)) {
        setError('服务响应与所选片段身份不匹配，未采用该响应。');
        return;
      }
      const location = fileHash && excerptHash && returned === excerptHash && returnedDialect === dialect ? 'file' : 'relative';
      setResult({ selected, result: raw, dialect, fileHash, excerptHash, location });
    } catch (failure) {
      if (active.current) setError(failure instanceof Error ? failure.message : '无法分析所选片段。');
    } finally {
      if (active.current) setBusy(false);
    }
  }

  const physicalUses = result?.result.uses.filter(row => !isUnverifiedPhysicalRead(row)) ?? [];
  const uncertainUses = result?.result.uses.filter(isUnverifiedUnionDerivation).length ?? 0;
  const unverifiedJoinCount = result?.result.uses.filter(isJoinVisibilityUnverified).length ?? 0;

  function fileSpan(range: Position): Position | null {
    if (!result || !excerptIndex || !indexes || result.location !== 'file') return null;
    const { sql, previewStart, previewEnd } = result.selected;
    const start = excerptIndex.utf16Offset(range.start), end = excerptIndex.utf16Offset(range.end);
    if (start == null || end == null || [start, end].some(i => sql[i - 1] === '\r' && sql[i] === '\n')) return null;
    const mapped = { start: previewStart + start - countThrough(indexes.collapsed, start),
      end: previewStart + end - countThrough(indexes.collapsed, end) };
    return mapped.start < mapped.end && mapped.end <= previewEnd &&
      display.slice(mapped.start, mapped.end) === visibleText(sql.slice(start, end)) ? mapped : null;
  }

  function locate(range: Position) {
    const box = preview.current;
    if (!box) return;
    const where = fileLocation(range.start);
    box.focus();
    box.setSelectionRange(range.start, range.end);
    const height = Number.parseFloat(getComputedStyle(box).lineHeight) || 20;
    box.scrollTop = Math.max(0, height * (where.line - 3));
    setReveal(`原文件第 ${where.line} 行第 ${where.column} 列`);
  }

  return <div className="subfield-app"><section className="subfield-main j-long-sql" aria-label="长 SQL 文件片段">
    <div className="actions">
      <h2>从长 SQL 文件选择片段</h2>
      <button type="button" className="btn" onClick={close}>返回原草稿</button>
    </div>
    <p>原文件：{name} · 仅在本机预览，原草稿和已有结果已保留。只发送确认后的所选原文，不发送整份文件或其他语句。</p>
    <p>未校验选区是否为完整语句。前序临时视图、SET、宏和 UDF 注册等不纳入；本句引用对象的跨语句来源未验证。片段模式不提供查键剪枝、行集验证或删除授权。</p>
    <label className="analysis-field">片段方言 <select className="select" value={dialect} disabled={busy}
      onChange={e => { setDialect(e.target.value as Dialect); setAcknowledged(false); setResult(null); setReveal(''); setError(''); }}>
      <option value="spark">Spark</option><option value="hive">Hive</option>
    </select></label>
    <label className="j-long-preview">本机 SQL 原文件预览
      <textarea ref={preview} value={display} readOnly wrap="off" rows={14} />
    </label>
    {reveal && <p role="status">{reveal}</p>}
    <div className="actions">
      <button type="button" className="btn" disabled={busy} onClick={confirmSelection}>确认所选片段</button>
      {selected && <p>第 {selected.lineFrom}–{selected.lineTo} 行 · 选中 {(selected.codePoints.end - selected.codePoints.start).toLocaleString('en-US')} / 65,536 码点</p>}
    </div>
    {selected && <>
      <label><input type="checkbox" checked={acknowledged} disabled={busy}
        onChange={e => setAcknowledged(e.target.checked)} /> 仅看片段：我确认只分析这段原文，未验证完整语句和前序上下文。</label>
      <div className="actions"><button type="button" className="btn-primary" disabled={busy || !acknowledged}
        onClick={() => void run()}>仅分析所选片段</button></div>
    </>}
    {busy && <p role="status">正在分析所选片段…</p>}
    {error && <p role="alert">{error}</p>}
    {result && excerptIndex && <section aria-label="所选片段结果">
      <h3>仅分析所选片段 · {name} 第 {result.selected.lineFrom}–{result.selected.lineTo} 行</h3>
      <p>{analysisStatusText(result.result, physicalUses.length > 0)} · 只说明片段内的静态证据，不代表整件完成。</p>
      {result.location === 'relative' && <p>无法核验原文件定位，仅显示所选片段内的相对坐标。</p>}
      {uncertainUses > 0 && <p>集合类型转换未核验：{uncertainUses} 条路径诊断不计为物理读取。</p>}
      {unverifiedJoinCount > 0 && <p>JOIN ON 来源未核验：{unverifiedJoinCount} 条诊断不计为物理读取。</p>}
      {physicalUses.length ? <ol>{physicalUses.map((row, i) => {
        const range = preferredJsonReadLocation([row], excerptIndex)?.position;
        const global = range && fileSpan(range);
        const origin = global && fileLocation(global.start);
        const relative = range && excerptIndex.editorPosition(range.start);
        const source = typeof row.source === 'string' && row.source;
        return <li key={i}>
          {source ? `${source}（片段内引用对象，跨语句来源未验证）` : '来源待确认'}
          {typeof row.column === 'string' && ` · ${row.column}`}{typeof row.path === 'string' && ` · ${row.path}`}
          {typeof row.clause === 'string' && ` · ${row.clause}`}
          {global && origin ? <button type="button" className="btn" onClick={() => locate(global)}>
            定位原文件 · 第 {origin.line} 行第 {origin.column} 列
          </button> : relative ? ` · 仅片段相对坐标：第 ${relative.lineNumber} 行第 ${relative.column} 列` : ' · 位置未确认'}
        </li>;
      })}</ol> : <p>此响应没有可展示的使用点；不能判断整份文件是否读取。</p>}
      {!!result.result.unknowns?.length && <p>服务报告的片段未决项：{result.result.unknowns.length}</p>}
      <details><summary>片段证据元数据</summary><pre>{JSON.stringify({
        file_sha256: result.fileHash, excerpt_sha256: result.excerptHash, byte_range: result.selected.byteRange,
        code_point_range: result.selected.codePoints, dialect: result.dialect, encoding: 'UTF-8',
        ranges: 'zero-based, half-open', bom: bom ? 'included in file byte offsets, excluded from code points and SQL' : 'absent',
      }, null, 2)}</pre></details>
    </section>}
  </section></div>;
}
