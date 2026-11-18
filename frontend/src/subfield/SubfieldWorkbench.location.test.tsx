import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { analyzeSubfieldSql } from '../api/client';
import type { Position, RecordRow } from './contract';
import type { createSQLPositionIndex } from './sqlPositionIndex';
import SubfieldWorkbench from './SubfieldWorkbench';

vi.mock('../api/client', () => ({ analyzeSubfieldSql: vi.fn() }));
vi.mock('./SubfieldEditor', () => ({ default: ({ sql, setSql, locate, positionIndex }: {
  sql: string; setSql: (value: string) => void; locate: Position | null;
  positionIndex: ReturnType<typeof createSQLPositionIndex> | null;
}) => <><textarea aria-label="输入 SQL" value={sql} onChange={event => setSql(event.target.value.replace(/\r?\n/g, '\r\n'))} />
  {locate && positionIndex && <output data-testid="editor-selection">
    {positionIndex.editorPosition(locate.start)?.lineNumber}:{positionIndex.editorPosition(locate.start)?.column}
    {' '}{positionIndex.excerpt(locate)?.match}
  </output>}</> }));
afterEach(() => { vi.mocked(analyzeSubfieldSql).mockReset(); });

// Fixed ALG02 source has the same text in a comment and two calls, after an astral character.
const sql = ["/* 😀 '$.item_id' */", 'WITH src AS (SELECT e.payload AS j FROM demo.events e)',
  "SELECT get_json_object(s.j, /* '$.item_id' */ '$.item_id') AS item_id,",
  "       get_json_object(s.j, '$.item_id') AS again FROM src s"].join('\r\n');
const path = { source: 'demo.events', column: 'payload', path: '$.item_id', path_tokens: [{ kind: 'key', value: 'item_id' }] };
const first = { ...path, kind: 'EXTRACT', role: 'VALUE', position: { start: 84, end: 99 } };
const second = { ...first, position: { start: 156, end: 171 }, json_path_position: { start: 177, end: 188 } };

async function analyze(uses: RecordRow[]) {
  vi.mocked(analyzeSubfieldSql).mockResolvedValue({ uses, mappings: [], unknowns: [] });
  render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '编辑 SQL 原文' }));
  fireEvent.change(await screen.findByRole('textbox', { name: '输入 SQL' }), { target: { value: sql } });
  fireEvent.click(screen.getByRole('button', { name: '分析 SQL' }));
  await screen.findByText(/服务结果 · 2 个使用点/);
}

it.each([
  ['3:47', [{ ...first, json_path_position: { start: 123, end: 134 } }, second]],
  ['4:29', [first, second]],
] as const)('locates the exact quoted API literal at %s ahead of call fallbacks', async (start, uses) => {
  await analyze([...uses]);
  fireEvent.click(screen.getByRole('button', { name: '定位读取证据' }));
  expect(await screen.findByTestId('editor-selection')).toHaveTextContent(`${start} '$.item_id'`);
  fireEvent.change(screen.getByRole('textbox', { name: '输入 SQL' }), { target: { value: `${sql}\r\n-- 修改` } });
  expect(screen.queryByTestId('editor-selection')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '定位读取证据' })).not.toBeInTheDocument();
});

it('locates the original call when the API literal is missing or out of bounds', async () => {
  await analyze([first, { ...second, json_path_position: { start: 177, end: 9999 } }]);
  fireEvent.click(screen.getByRole('button', { name: '定位读取调用' }));
  expect(await screen.findByTestId('editor-selection')).toHaveTextContent('3:8 get_json_object');
});
