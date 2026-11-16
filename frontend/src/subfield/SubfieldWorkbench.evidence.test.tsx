/// <reference types="node" />
import { Blob as NodeBlob } from 'node:buffer';
import { createHash, webcrypto } from 'node:crypto';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { analyzeSubfieldSql } from '../api/client';
import SubfieldWorkbench from './SubfieldWorkbench';
import { buildEvidenceBundle } from './evidenceBundle';
import { textMapSQL } from './workbench.mjs';

vi.mock('../api/client', () => ({ analyzeSubfieldSql: vi.fn() }));
afterEach(() => { vi.mocked(analyzeSubfieldSql).mockReset(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('returns to the full table graph after reanalyzing a selected JSON path', async () => {
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

  fireEvent.click(tryExample);
  await screen.findByText('服务结果 · 2 个使用点');
  expect(mock).toHaveBeenCalledTimes(2);
  expect(screen.getByRole('button', { name: '表血缘' })).toHaveAttribute('aria-pressed', 'true');
  expect(container.querySelectorAll('.canvas-node')).toHaveLength(4);
});

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
  const first = await screen.findByRole('checkbox', { name: /item_id/ });
  fireEvent.click(first);
  fireEvent.click(screen.getByRole('button', { name: '评审剪枝' }));
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
  const root = await screen.findByRole('checkbox', { name: /item_id/ });
  fireEvent.click(root);
  fireEvent.click(screen.getByRole('button', { name: '评审剪枝' }));
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
  fireEvent.change(select, { target: { value: screen.getByRole<HTMLOptionElement>('option', { name: '文本 Map 查键示例' }).value } });
  fireEvent.click(screen.getByRole('button', { name: '分析 SQL' }));
  expect(await screen.findByText('构造示例')).toBeVisible();
  const downloadSummary = screen.getByText('分析来源与证据下载');
  expect(downloadSummary.closest('details')).not.toHaveAttribute('open');
  fireEvent.click(downloadSummary);
  expect(downloadSummary.closest('details')).toHaveAttribute('open');
  expect(screen.getByText('合成示例 · 仅分析本次提交 SQL')).toBeVisible();
  const download = () => fireEvent.click(screen.getByRole('button', { name: '下载证据（JSON）' }));
  download();
  await waitFor(() => expect(downloads).toHaveBeenCalledTimes(1));
  const analysis = JSON.parse(await downloads.mock.calls[0][0].text());
  expect(analysis.request).toEqual({ sql: textMapSQL, dialect: 'hive' });
  expect(analysis.origin).toEqual({ kind: 'CONSTRUCTED', verification: 'NOT_APPLICABLE' });
  expect(analysis.response.extra_service_data).toEqual({ keep: true });
  expect(analysis.locations.find((row: { fact_ref: string }) => row.fact_ref === '/unknowns/0').original_span).toBeNull();
  // Even matching supplied bytes and a non-empty receipt string are not a trusted archive witness.
  const bytes = new TextEncoder().encode(textMapSQL);
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

  const root = screen.getByRole('checkbox', { name: /id ·/ });
  fireEvent.click(root);
  fireEvent.click(screen.getByRole('button', { name: '评审剪枝' }));
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
