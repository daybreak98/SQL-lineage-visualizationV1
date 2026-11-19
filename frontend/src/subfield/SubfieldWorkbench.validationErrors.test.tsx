import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import SubfieldWorkbench from './SubfieldWorkbench';

vi.mock('./SubfieldEditor', () => ({ default: ({ sql, setSql }: { sql: string; setSql: (text: string) => void }) =>
  <textarea aria-label="输入 SQL" value={sql} onChange={e => setSql(e.target.value)} /> }));
afterEach(() => vi.unstubAllGlobals());

async function submit(detail: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 422 })));
  render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '编辑 SQL 原文' }));
  const editor = await screen.findByRole('textbox', { name: '输入 SQL' });
  fireEvent.change(editor, { target: { value: 'SELECT private_column FROM private_table' } });
  fireEvent.click(screen.getByRole('button', { name: '分析 SQL' }));
  return screen.findByRole('alert');
}

it('uses legacy field and validation type for guidance without copying validation input or raw messages', async () => {
  const alert = await submit([
    { loc: ['body', 'SubfieldRequest', 'sql'], type: 'string_too_long', msg: 'String should have at most 65536 characters: private_column',
      input: 'SELECT private_column FROM private_table', ctx: { max_length: 65536 } },
    { loc: ['body', 'SubfieldRequest', 'dialect'], type: 'literal_error', msg: "Input should be 'hive' or 'spark'", input: 'private_dialect' },
    { loc: ['body', 'CompositionRequest', 'snapshots'], type: 'missing', msg: 'Field required', input: { sql: 'private_column' } },
  ]);
  expect(alert).toHaveTextContent(/65,536.*缩短.*方言.*Spark.*Hive/);
  expect(alert).not.toHaveTextContent(/private_|String should|Field required/);
});

it('explains the current structured schema conflict without echoing identifiers or the error input', async () => {
  const alert = await submit({ code: 'CONFLICTING_SOURCE_SCHEMAS', relations: ['private_table'],
    input: 'SELECT private_column' });
  expect(alert).toHaveTextContent(/源列清单.*冲突.*检查/);
  expect(alert).not.toHaveTextContent(/private_/);
});
