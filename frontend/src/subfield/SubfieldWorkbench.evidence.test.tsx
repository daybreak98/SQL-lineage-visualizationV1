/// <reference types="node" />
import { Blob as NodeBlob } from 'node:buffer';
import { createHash, webcrypto } from 'node:crypto';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { analyzeSubfieldSql } from '../api/client';
import SubfieldWorkbench from './SubfieldWorkbench';
import { buildEvidenceBundle } from './evidenceBundle';
import { textMapSQL } from './workbench.mjs';

vi.mock('../api/client', () => ({ analyzeSubfieldSql: vi.fn() }));
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

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
  const select = screen.getByLabelText('加载示例') as HTMLSelectElement;
  fireEvent.change(select, { target: { value: screen.getByRole<HTMLOptionElement>('option', { name: '文本 Map 查键示例' }).value } });
  fireEvent.click(screen.getByRole('button', { name: '分析 SQL' }));
  expect(await screen.findByText('合成示例 · 仅分析本次提交 SQL')).toBeInTheDocument();
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
