/// <reference types="node" />
import { Blob as NodeBlob } from 'node:buffer';
import { createHash, webcrypto } from 'node:crypto';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { analyzeSubfieldSql } from '../api/client';
import SubfieldWorkbench from './SubfieldWorkbench';
import { buildEvidenceBundle } from './evidenceBundle';
import examples from './archive-evidence-examples.json';

vi.mock('./SubfieldEditor', () => ({ default: ({ sql, setSql }: { sql: string; setSql: (value: string) => void }) =>
  <textarea aria-label="输入 SQL" value={sql} onChange={event => setSql(event.target.value)} /> }));
vi.mock('../api/client', () => ({ analyzeSubfieldSql: vi.fn() }));
afterEach(() => { vi.mocked(analyzeSubfieldSql).mockReset(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('clears the old JSON selection and opens the table overview for a new response without JSON paths', async () => {
  const input = { source: 'demo.events', column: 'payload', path: '$.item_id',
    path_tokens: [{ kind: 'key', value: 'item_id' }] };
  const whole = { ...input, path: '$', path_tokens: [] };
  const mock = vi.mocked(analyzeSubfieldSql).mockResolvedValue({
    uses: [input, whole],
    mappings: [input, whole].map((path, i) => ({
      statement: 1, scope: '1:1', slot: i + 1, root: true, output: i === 0 ? 'item_id' : 'raw_payload',
      terminal_binding: 'SQL_NAMED_RELATION_COLUMN', inputs: [path],
    })),
    unknowns: [],
  });
  const { container } = render(<SubfieldWorkbench />);
  const tryExample = screen.getByRole('button', { name: '试用示例' });
  fireEvent.click(tryExample);
  await screen.findByText('服务结果 · 2 个使用点');
  const search = screen.getByRole('searchbox');
  fireEvent.change(search, { target: { value: 'item_id' } });
  fireEvent.keyDown(search, { key: 'Enter' });
  expect(screen.getByRole('button', { name: 'JSON 排查' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: '整列（$）' })).toBeVisible();
  expect(container.querySelectorAll('.canvas-node')).toHaveLength(3);

  mock.mockResolvedValueOnce({ uses: [whole], mappings: [{ statement: 1, scope: '1:1', slot: 1, root: true, output: 'new_output', inputs: [whole] }], unknowns: [] });
  fireEvent.click(tryExample);
  await screen.findByText('服务结果 · 1 个使用点');
  expect(mock).toHaveBeenCalledTimes(2);
  expect(screen.getByRole('button', { name: '表血缘' })).toHaveAttribute('aria-pressed', 'true');
  expect(container.querySelector('.canvas-node[title^="new_output"]')).toBeVisible();
  expect(container).not.toHaveTextContent('$.item_id');
});

function analyzeAndFocusPath(source: string, path: string) {
  fireEvent.click(screen.getByRole('button', { name: '试用示例' }));
  return screen.findByText(/服务结果 · \d+ 个使用点/).then(() => {
    const search = screen.getByRole('searchbox');
    fireEvent.change(search, { target: { value: `${source} · j · ${path}` } });
    fireEvent.keyDown(search, { key: 'Enter' });
    expect(screen.getByRole('button', { name: 'JSON 排查' })).toHaveAttribute('aria-pressed', 'true');
  });
}

const kindPath = (source: string) => ({ source, column: 'j', path: '$.kind',
  path_tokens: [{ kind: 'key', value: 'kind' }] });

it('keeps the source and both value projections when focusing a fixed-map value path', async () => {
  // Map key/value projection facts from the analyzer, with no asserted port reads.
  const origin = kindPath('lab.events');
  vi.mocked(analyzeSubfieldSql).mockResolvedValue({
    uses: [origin, origin], unknowns: [],
    mappings: ['1:1', '1:2'].flatMap((scope, i) => ['k', 'v'].map((output, j) => ({
      output, statement: 1, scope, slot: j + 1, root: i === 1, kind: 'DERIVED',
      generator_ports: [`1:1:explode:${j + 1}`], inputs: j ? [origin] : [],
    }))),
  });
  const { container } = render(<SubfieldWorkbench />);
  await analyzeAndFocusPath('lab.events', '$.kind');
  expect(container.querySelector('[data-role="relation"][title="lab.events"]')).toBeVisible();
  expect(container.querySelector('[data-role="path"][title="j · $.kind"]')).toBeVisible();
  expect([...container.querySelectorAll('.canvas-node')].map(n => n.getAttribute('title'))).toEqual([
    'lab.events', 'j · $.kind', 'v · 1:2', 'v · 1:1',
  ]);
  const edges = [...container.querySelectorAll('[data-edge]')];
  expect(edges).toHaveLength(3);
  expect(edges.every(edge => edge.getAttribute('aria-label')!.includes('j · $.kind'))).toBe(true);
});

it('keeps both UNION branches with the same source path as separate evidence', async () => {
  const origin = kindPath('lab.events');
  vi.mocked(analyzeSubfieldSql).mockResolvedValue({
    uses: [origin, origin], unknowns: [],
    mappings: [origin, origin].map((input, i) => ({
      statement: 1, scope: `1:${i + 1}`, slot: 1, root: false, output: 'kind', kind: 'EXTRACT', inputs: [input],
    })),
  });
  const { container } = render(<SubfieldWorkbench />);
  await analyzeAndFocusPath('lab.events', '$.kind');
  expect([...container.querySelectorAll('.canvas-node')].map(n => n.getAttribute('title'))).toEqual([
    'lab.events', 'j · $.kind', 'kind · 1:1', 'kind · 1:2',
  ]);
  const edges = [...container.querySelectorAll('[data-edge]')];
  expect(edges).toHaveLength(3);
  for (const scope of ['1:1', '1:2']) {
    const branch = edges.find(edge => edge.getAttribute('aria-label')!.includes(`kind · ${scope}`));
    expect(branch).toBeDefined();
    fireEvent.click(branch!);
    expect(container.querySelector('.subfield-detail-body h3')).toHaveTextContent(`kind · ${scope}`);
  }
});

async function openReview() {
  fireEvent.click(await screen.findByText(/^检查范围：全部/));
  fireEvent.click(screen.getByText('高级核查记录'));
}

it('clears pinned review evidence when the protected outputs change', async () => {
  // The pinned report normally scrolls into view; this test only checks the evidence state.
  vi.stubGlobal('requestAnimationFrame', vi.fn());
  vi.mocked(analyzeSubfieldSql).mockImplementation(async request => ({
    uses: [],
    mappings: ['item_id', 'raw_payload'].map((output, i) => ({
      statement: 1, scope: '1:1', slot: i + 1, root: true, output,
    })),
    unknowns: [],
    ...(request.protected_outputs ? { review: {
      findings: [{ decision: 'RETAIN_WHOLE', basis: '旧评审证据', position: { start: 0, end: 3 } }],
    } } : {}),
  }));
  const { container } = render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '试用示例' }));
  await openReview();
  const first = await screen.findByRole('checkbox', { name: /item_id/ });
  fireEvent.click(first);
  fireEvent.click(screen.getByRole('button', { name: '核查所选输出' }));
  const finding = await screen.findByText(/保留与待验证项 · 1 项/);
  const details = finding.closest('details')!;
  details.open = true;
  fireEvent(details, new Event('toggle'));
  fireEvent.click(await screen.findByRole('button', { name: /旧评审证据/ }));
  const inspector = container.querySelector('.subfield-detail-body')!;
  expect(inspector).toHaveTextContent('旧评审证据');

  fireEvent.click(screen.getByRole('checkbox', { name: /raw_payload/ }));
  expect(screen.queryByText(/保留与待验证项 · 1 项/)).not.toBeInTheDocument();
  expect(inspector).not.toHaveTextContent('旧评审证据');
  expect(screen.getByText(/将下载：分析证据/)).toBeInTheDocument();

  fireEvent.click(container.querySelector('.canvas-node[title^="item_id"]')!);
  expect(inspector.querySelector('h3')).toHaveTextContent('item_id');
  fireEvent.click(first);
  expect(inspector.querySelector('h3')).toHaveTextContent('item_id');
});

it('lets the current analysis download proceed while invalidated review hashing settles', async () => {
  let rejectOld!: (error: Error) => void;
  let deliverCurrent!: (hash: ArrayBuffer) => void;
  const oldDigest = new Promise<ArrayBuffer>((_, reject) => { rejectOld = reject; });
  const currentDigest = new Promise<ArrayBuffer>(resolve => { deliverCurrent = resolve; });
  const digest = vi.fn().mockReturnValueOnce(oldDigest).mockReturnValueOnce(currentDigest);
  vi.stubGlobal('crypto', { randomUUID: () => webcrypto.randomUUID(), subtle: { digest } });
  vi.stubGlobal('Blob', NodeBlob);
  const downloads = vi.fn<(blob: NodeBlob) => string>(() => 'blob:test');
  vi.stubGlobal('URL', new Proxy(URL, { get(target, key, receiver) {
    if (key === 'createObjectURL') return downloads;
    if (key === 'revokeObjectURL') return () => {};
    return Reflect.get(target, key, receiver);
  } }));
  const clickFile = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  const mock = vi.mocked(analyzeSubfieldSql).mockImplementation(async request => ({
    uses: [],
    mappings: [{ statement: 1, scope: '1:1', slot: 1, root: true, output: 'item_id' }],
    unknowns: [],
    coverage: { parsed: true, dialect: request.dialect, sql_sha256: createHash('sha256').update(request.sql).digest('hex') },
    ...(request.protected_outputs ? { review: { findings: [] } } : {}),
  }));
  render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '试用示例' }));
  await openReview();
  const root = await screen.findByRole('checkbox', { name: /item_id/ });
  expect(root).toBeChecked();
  fireEvent.click(screen.getByRole('button', { name: '核查所选输出' }));
  await screen.findByText(/将下载：剪枝评审证据/);
  fireEvent.click(screen.getByText('分析来源与证据下载'));
  const button = () => screen.getByRole('button', { name: '下载证据（JSON）' });
  fireEvent.click(button());
  await waitFor(() => expect(digest).toHaveBeenCalledTimes(1));

  fireEvent.click(root);
  expect(screen.getByText(/将下载：分析证据/)).toBeVisible();
  expect(button()).toBeEnabled();
  fireEvent.click(button());
  await waitFor(() => expect(digest).toHaveBeenCalledTimes(2));
  await act(async () => { rejectOld(new Error('旧评审哈希失败')); await oldDigest.catch(() => {}); });
  expect(screen.queryByText('旧评审哈希失败')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '正在准备证据…' })).toBeDisabled();
  expect(clickFile).not.toHaveBeenCalled();

  deliverCurrent(await webcrypto.subtle.digest('SHA-256', new TextEncoder().encode(mock.mock.calls[0][0].sql)));
  await waitFor(() => expect(clickFile).toHaveBeenCalledTimes(1));
  expect(downloads).toHaveBeenCalledTimes(1);
  const bundle = JSON.parse(await downloads.mock.calls[0][0].text());
  expect(bundle.request).toEqual(mock.mock.calls[0][0]);
  expect(bundle.response).not.toHaveProperty('review');
  expect(button()).toBeEnabled();
});

it('downloads the exact request and response and invalidates only the review when roots change', async () => {
  vi.stubGlobal('crypto', webcrypto);
  vi.stubGlobal('Blob', NodeBlob);
  const downloads = vi.fn<(blob: NodeBlob) => string>(() => 'blob:test');
  vi.stubGlobal('URL', new Proxy(URL, { get(target, key, receiver) {
    if (key === 'createObjectURL') return downloads;
    if (key === 'revokeObjectURL') return () => {};
    return Reflect.get(target, key, receiver);
  } }));
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  const mock = vi.mocked(analyzeSubfieldSql).mockImplementation(async request => ({
    uses: [], mappings: [{ statement: 1, scope: '1:1', slot: 1, root: true, output: 'id' }],
    unknowns: [{ code: 'UNKNOWN_BINDING', position: { start: 0, end: 1 } }],
    coverage: { parsed: true, complete: false, dialect: request.dialect,
      sql_sha256: createHash('sha256').update(request.sql).digest('hex') },
    extra_service_data: { keep: true },
    ...(request.protected_outputs ? { review: { findings: [] } } : {}),
  }));
  render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByText('示例与分析选项'));
  const select = screen.getByLabelText('加载示例') as HTMLSelectElement;
  fireEvent.change(select, { target: { value: screen.getByRole<HTMLOptionElement>('option', { name: /合成文本 Map 摘录/ }).value } });
  fireEvent.click(screen.getByRole('button', { name: '分析 SQL' }));
  expect(await screen.findByText('合成摘录 · 仅此片段')).toBeVisible();
  expect((await screen.findAllByText(/合成摘录 · #\d+.*清单声明/))[0]).toBeInTheDocument();
  const downloadSummary = screen.getByText('分析来源与证据下载');
  expect(downloadSummary.closest('details')).not.toHaveAttribute('open');
  fireEvent.click(downloadSummary);
  expect(downloadSummary.closest('details')).toHaveAttribute('open');
  const download = () => fireEvent.click(screen.getByRole('button', { name: '下载证据（JSON）' }));
  download();
  await waitFor(() => expect(downloads).toHaveBeenCalledTimes(1));
  const analysis = JSON.parse(await downloads.mock.calls[0][0].text());
  expect(analysis.request).toEqual({ sql: examples.r24.sql, dialect: 'hive' });
  expect(analysis.origin.verification).toBe('DECLARED');
  expect(analysis.response.extra_service_data).toEqual({ keep: true });
  expect(analysis.locations.find((row: { fact_ref: string }) => row.fact_ref === '/unknowns/0').original_span).toBeNull();
  // Even matching supplied bytes and a non-empty receipt string are not a trusted archive witness.
  const bytes = new TextEncoder().encode(examples.r24.sql);
  const untrusted = {
    requestId: 'negative-control', capturedAt: analysis.captured_at, request: analysis.request,
    rawResponse: analysis.response, originalBytes: bytes,
    origin: { kind: 'ORIGINAL' as const, verification_ref: 'x', encoding: 'utf-8' as const,
      original_size: bytes.length, original_sha256: analysis.submitted_sql_sha256,
      range_sha256: analysis.submitted_sql_sha256, byte_range: { start: 0, end: bytes.length } },
  };
  const notVerified = await buildEvidenceBundle(untrusted);
  expect(notVerified.origin.verification).toBe('DECLARED');
  expect(notVerified.origin).not.toHaveProperty('verification_ref');
  expect(notVerified.locations.every(row => row.original_span === null)).toBe(true);

  await openReview();
  const root = screen.getByRole('checkbox', { name: /id（语句/ });
  expect(root).toBeChecked();
  fireEvent.click(screen.getByRole('button', { name: '核查所选输出' }));
  await screen.findByText(/将下载：剪枝评审证据/);
  download();
  await waitFor(() => expect(downloads).toHaveBeenCalledTimes(2));
  const review = JSON.parse(await downloads.mock.calls[1][0].text());
  expect(review.request).toEqual({ ...analysis.request, protected_outputs: [{ statement: 1, scope: '1:1', slot: 1 }] });
  expect(review.response.review).toEqual({ findings: [] });
  expect(review.request_id).not.toBe(analysis.request_id);
  expect(mock).toHaveBeenCalledTimes(2);
  fireEvent.click(root);
  expect(screen.getByText(/将下载：分析证据/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('方言'), { target: { value: 'spark' } });
  expect(screen.queryByRole('button', { name: '下载证据（JSON）' })).not.toBeInTheDocument();
});

it('checks an ad-hoc key with exact request identity and never borrows observations from another output range', async () => {
  const origin = kindPath('lab.events');
  const sql = "SELECT get_json_object(t.j, '$.kind') AS kind, t.j AS raw FROM lab.events t";
  const root = (slot: number, output: string) => ({ statement: 1, scope: '1:1', slot, root: true, output, inputs: [origin] });
  const mock = vi.mocked(analyzeSubfieldSql).mockImplementation(async request => ({
    uses: [origin, origin], mappings: [root(1, 'kind'), root(2, 'raw')], unknowns: [],
    ...(request.candidate_keys ? { review: { candidate_assessment: { status: 'UNKNOWN', entries: [
      { source: 'other.events', column: 'j', key: 'kind', status: 'OBSERVED' },
      { source: 'lab.events', column: 'j', key: request.candidate_keys[0].keys[0], status:
        request.protected_outputs?.length === 2 ? 'UNKNOWN' : request.candidate_keys[0].keys[0] === 'kind' ? 'OBSERVED' : 'NOT_OBSERVED_NEEDS_VALIDATION' },
    ] } } } : {}),
  }));
  const { container } = render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '编辑 SQL 原文' }));
  fireEvent.change(await screen.findByRole('textbox', { name: '输入 SQL' }), { target: { value: sql } });
  fireEvent.click(screen.getByRole('button', { name: '分析 SQL' }));
  expect(await screen.findByText('1 条 JSON 路径')).toBeVisible();
  expect(screen.getByText('2 个不同的下游输出')).toBeVisible();
  const path = screen.getByRole('textbox', { name: 'JSON 路径' });
  const check = () => fireEvent.click(screen.getByRole('button', { name: '检查键' }));
  const result = () => container.querySelector('.j-path-result');
  fireEvent.change(path, { target: { value: '$.kind' } });
  check();
  await waitFor(() => expect(result()).toHaveTextContent('暂不能判断'));
  expect(mock).toHaveBeenLastCalledWith({ sql, dialect: 'spark', protected_outputs: [
    { statement: 1, scope: '1:1', slot: 1 }, { statement: 1, scope: '1:1', slot: 2 },
  ], candidate_keys: [{ source: 'lab.events', column: 'j', keys: ['kind'] }] });
  fireEvent.click(screen.getByText(/^检查范围：全部/));
  fireEvent.click(screen.getByRole('checkbox', { name: /^raw/ }));
  expect(result()).toBeNull();
  check();
  await waitFor(() => expect(result()).toHaveTextContent('已看到读取'));
  expect(result()).not.toHaveTextContent('raw（语句');
  fireEvent.change(path, { target: { value: 'absent' } });
  check();
  await waitFor(() => expect(result()).toHaveTextContent('本次未见读取'));
  expect(result()).toHaveTextContent('键是否存在、修改是否有影响仍需核对');
  fireEvent.change(path, { target: { value: '$.kind.nested' } });
  check();
  expect(result()).toHaveTextContent('只支持字面顶层键');
  expect(mock).toHaveBeenCalledTimes(4);
  fireEvent.click(screen.getByRole('button', { name: '按字面键名' }));
  const literal = screen.getByRole('textbox', { name: 'JSON 顶层键名' });
  fireEvent.change(literal, { target: { value: ' $.名字.😀 ' } });
  check();
  await waitFor(() => expect(result()).toHaveTextContent('本次未见读取'));
  expect(mock.mock.lastCall?.[0].candidate_keys).toEqual([{ source: 'lab.events', column: 'j', keys: [' $.名字.😀 '] }]);
  fireEvent.click(screen.getByRole('button', { name: '检查空键' }));
  await waitFor(() => expect(result()).toHaveTextContent('空键'));
  expect(mock.mock.lastCall?.[0].candidate_keys).toEqual([{ source: 'lab.events', column: 'j', keys: [''] }]);
  fireEvent.change(literal, { target: { value: '😀'.repeat(257) } });
  check();
  expect(result()).toHaveTextContent('最多 256 个字符');
  expect(mock).toHaveBeenCalledTimes(6);

});

it('keeps the SQL count separate from key review and submits only visibly checked output ports', async () => {
  const input = kindPath('src');
  const hit = { statement: 1, scope: '1:2', slot: 1 };
  const whole = { ...hit, slot: 2 };
  const mock = vi.mocked(analyzeSubfieldSql).mockImplementation(async request => ({
    uses: [input], unknowns: [],
    mappings: [{ ...hit, root: true, output: 'hit', inputs: [input] }, { ...whole, root: true, output: 'whole' }],
    ...(request.candidate_keys ? { review: request.protected_outputs?.length === 2 ? {
      candidate_assessment: { entries: [], reason: 'PROTECTED_WHOLE_CARRIER' },
      findings: [{ decision: 'RETAIN_WHOLE', protected_output: whole }],
    } : { candidate_assessment: { entries: [{ source: 'src', column: 'j', key: 'b', status: 'NOT_OBSERVED_NEEDS_VALIDATION' }] } } } : {}),
  }));
  const { container } = render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '试用示例' }));
  const summary = await screen.findByText('检查范围：全部 2 个输出（默认）');
  expect(screen.getByText('SQL 分析待确认项：0')).toBeVisible();
  expect(screen.getByText('键检查：尚未检查')).toBeVisible();
  fireEvent.click(summary);
  const all = screen.getByRole('checkbox', { name: '全选' });
  const hitBox = screen.getByRole('checkbox', { name: /^hit/ });
  const wholeBox = screen.getByRole('checkbox', { name: /^whole/ });
  for (const input of [all, hitBox, wholeBox]) expect(input).toBeChecked();
  expect(mock).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByRole('textbox', { name: 'JSON 路径' }), { target: { value: '$.b' } });
  const check = screen.getByRole('button', { name: '检查键' });
  const result = () => container.querySelector('.j-path-result');
  fireEvent.click(check);
  await waitFor(() => expect(result()).toHaveTextContent('暂不能判断'));
  expect(result()).toHaveTextContent('整列依赖');
  expect(result()).toHaveTextContent('涉及输出：whole');
  expect(result()).toHaveTextContent('本次检查范围：全部 2 个输出');
  expect(mock.mock.lastCall?.[0].protected_outputs).toEqual([hit, whole]);
  fireEvent.click(wholeBox);
  expect(all).toBePartiallyChecked();
  expect(summary).toHaveTextContent('已选 1 / 2 个输出（自定义）');
  expect(screen.getByText(/此前结果已失效/)).toBeVisible();
  expect(result()).toBeNull();
  fireEvent.click(check);
  await waitFor(() => expect(result()).toHaveTextContent('本次未见读取'));
  expect(mock.mock.lastCall?.[0].protected_outputs).toEqual([hit]);
  fireEvent.click(hitBox);
  expect(summary).toHaveTextContent('尚未选择输出（0 / 2）');
  expect(check).toBeDisabled();
  fireEvent.submit(check.closest('form')!);
  expect(mock).toHaveBeenCalledTimes(3);
  fireEvent.click(screen.getByRole('button', { name: '恢复全部输出' }));
  expect(summary).toHaveTextContent('全部 2 个输出（默认）');
  for (const input of [all, hitBox, wholeBox]) expect(input).toBeChecked();
  expect(result()).toBeNull();
  expect(mock).toHaveBeenCalledTimes(3);
});

it('reports a missing SQL unknowns list as unavailable while retaining the evidence view', async () => {
  vi.mocked(analyzeSubfieldSql).mockResolvedValue({ uses: [kindPath('src')], mappings: [] });
  render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '试用示例' }));
  expect(await screen.findByText('SQL 分析待确认项：未提供')).toBeVisible();
  expect(screen.getByText('1 条 JSON 路径')).toBeVisible();
  expect(screen.getByText('检查范围：没有可选输出')).toBeVisible();
  expect(screen.getByRole('button', { name: '检查键' })).toBeDisabled();
});
