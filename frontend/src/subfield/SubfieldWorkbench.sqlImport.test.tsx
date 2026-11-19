import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { analyzeSubfieldSql } from '../api/client';
import SubfieldWorkbench from './SubfieldWorkbench';

vi.mock('../api/client', () => ({ analyzeSubfieldSql: vi.fn() }));
vi.mock('./SubfieldEditor', () => ({ default: ({ sql, setSql }: { sql: string; setSql: (value: string) => void }) =>
  <textarea aria-label="输入 SQL" value={sql} onChange={event => setSql(event.target.value)} /> }));

it('loads an intentional UTF-8 SQL replacement locally and waits for manual analysis', async () => {
  const mock = vi.mocked(analyzeSubfieldSql).mockResolvedValue({ uses: [], mappings: [], unknowns: [] });
  const sql = "-- 😀 本地草稿\r\nSELECT 1 AS hit";
  render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '编辑 SQL 原文' }));
  const editor = await screen.findByRole('textbox', { name: '输入 SQL' });
  fireEvent.change(editor, { target: { value: 'SELECT 0 AS draft' } });
  const input = screen.getByLabelText('选择 SQL 文件');
  fireEvent.change(input, { target: { files: [new File(['x'.repeat(512 * 1024 + 1)], 'large.sql')] } });
  expect(await screen.findByText(/超过.*512 KiB/)).toBeVisible();
  expect(editor).toHaveValue('SELECT 0 AS draft');
  expect(mock).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { files: [new File(['\uFEFF', sql], 'sample.sql')] } });
  const replace = await screen.findByRole('button', { name: '替换当前 SQL 草稿' });
  expect(editor).toHaveValue('SELECT 0 AS draft');
  fireEvent.click(replace);
  expect(editor).toHaveValue(sql.replace('\r\n', '\n'));
  expect(mock).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '分析 SQL' }));
  expect(mock).toHaveBeenCalledExactlyOnceWith({ sql, dialect: 'spark' });
  await screen.findByText(/服务结果 ·/);
});
