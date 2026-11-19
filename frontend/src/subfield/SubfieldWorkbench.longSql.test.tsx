import { fireEvent, render, screen, within } from '@testing-library/react';
import { createHash } from 'node:crypto';
import { afterEach, expect, it, vi } from 'vitest';
import { analyzeSubfieldSql } from '../api/client';
import SubfieldWorkbench from './SubfieldWorkbench';

vi.mock('../api/client', () => ({ analyzeSubfieldSql: vi.fn() }));
vi.mock('./SubfieldEditor', () => ({ default: ({ sql, setSql }: { sql: string; setSql: (value: string) => void }) =>
  <textarea aria-label="输入 SQL" value={sql} onChange={e => setSql(e.target.value)} /> }));
afterEach(() => { vi.mocked(analyzeSubfieldSql).mockReset(); vi.unstubAllGlobals(); });

it('preserves the draft and submits only an explicitly selected long-file excerpt with mapped source coordinates', async () => {
  const prefix = "-- 😀 " + 'x'.repeat(66_000) + "\r\nCREATE TEMP VIEW stage AS SELECT payload FROM src;\r\n";
  const sql = "/* 😀 */\r\nSELECT get_json_object(payload,'$.a') AS a FROM stage";
  const literal = "'$.a'";
  const start = Array.from(sql.slice(0, sql.indexOf(literal))).length;
  const content = '\uFEFF' + prefix + sql;
  vi.stubGlobal('crypto', { subtle: { digest: async (_: string, data: Uint8Array) =>
    Uint8Array.from(createHash('sha256').update(data).digest()).buffer } });
  const mock = vi.mocked(analyzeSubfieldSql).mockResolvedValue({
    coverage: { parsed: true, dialect: 'spark', sql_sha256: createHash('sha256').update(sql).digest('hex') },
    uses: [{ source: 'stage', column: 'payload', path: '$.a', kind: 'EXTRACT', role: 'VALUE',
      json_path_position: { start, end: start + literal.length } }], mappings: [], unknowns: [],
  });
  render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '编辑 SQL 原文' }));
  fireEvent.change(await screen.findByRole('textbox', { name: '输入 SQL' }), { target: { value: 'SELECT 42 AS draft' } });
  fireEvent.change(screen.getByLabelText('选择 SQL 文件'), { target: { files: [new File([content], 'long.sql')] } });
  const preview = await screen.findByRole('textbox', { name: '本机 SQL 原文件预览' }) as HTMLTextAreaElement;
  expect(preview.value).toContain('CREATE TEMP VIEW');
  expect(mock).not.toHaveBeenCalled();
  const hit = preview.value.indexOf('/* 😀 */');
  preview.setSelectionRange(hit, preview.value.length);
  fireEvent.click(screen.getByRole('button', { name: '确认所选片段' }));
  const run = screen.getByRole('button', { name: '仅分析所选片段' });
  expect(run).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', { name: /仅看片段/ }));
  expect(mock).not.toHaveBeenCalled();
  fireEvent.click(run);
  expect(mock).toHaveBeenCalledExactlyOnceWith({ sql, dialect: 'spark' });
  const result = within(await screen.findByRole('region', { name: '所选片段结果' }));
  expect(result.getByText(/第 3–4 行/)).toBeVisible();
  expect(result.getByText(/stage.*跨语句来源未验证/)).toBeVisible();
  expect(screen.queryByRole('button', { name: '检查键' })).not.toBeInTheDocument();
  fireEvent.click(result.getByRole('button', { name: /定位原文件.*第 4 行/ }));
  expect(preview.value.slice(preview.selectionStart, preview.selectionEnd)).toBe(literal);
  const metadata = result.getByText(/file_sha256/).textContent!;
  const info = JSON.parse(metadata);
  expect(info.file_sha256).toBe(createHash('sha256').update(content).digest('hex'));
  expect(info.byte_range).toEqual({ start: Buffer.byteLength('\uFEFF' + prefix), end: Buffer.byteLength(content) });
  expect(info.code_point_range.start).toBe(Array.from(prefix).length);
  fireEvent.click(screen.getByRole('button', { name: '返回原草稿' }));
  expect(await screen.findByRole('textbox', { name: '输入 SQL' })).toHaveValue('SELECT 42 AS draft');
});
