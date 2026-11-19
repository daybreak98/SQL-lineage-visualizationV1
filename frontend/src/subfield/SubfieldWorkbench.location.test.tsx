import { fireEvent, render, screen, within } from '@testing-library/react';
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

const receiptSql = "SELECT get_json_object(t.other, '$.a') AS original, get_json_object(t.j, '$.a.x') AS x, get_json_object(t.j, '$.a.y') AS y FROM demo.events t";
const read = (column: string, path: string, located = true) => {
  const literal = `'${path}'`;
  const start = receiptSql.indexOf(literal);
  return { source: 'demo.events', column, path, kind: 'EXTRACT', role: 'VALUE',
    path_tokens: path.slice(2).split('.').map(value => ({ kind: 'key', value })),
    ...(located ? { json_path_position: { start, end: start + literal.length } } : {}) };
};
const original = read('other', '$.a'), x = read('j', '$.a.x'), y = read('j', '$.a.y');

async function checkReceipt(uses: RecordRow[], status = 'OBSERVED', sql = receiptSql, key = 'a', projected = x) {
  const mock = vi.mocked(analyzeSubfieldSql).mockImplementation(async request => ({
    uses, unknowns: [], mappings: [{ statement: 1, scope: '1:1', slot: 1, root: true, output: 'x', inputs: [projected] },
      { statement: 1, scope: '1:1', slot: 2, root: true, output: 'original', inputs: [original] }],
    ...(request.candidate_keys ? { review: { candidate_assessment: { entries: [
      { source: 'demo.events', column: 'j', key, status },
    ] } } } : {}),
  }));
  render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '编辑 SQL 原文' }));
  fireEvent.change(await screen.findByRole('textbox', { name: '输入 SQL' }), { target: { value: sql } });
  fireEvent.click(screen.getByRole('button', { name: '分析 SQL' }));
  await screen.findByText(/服务结果 ·/);
  fireEvent.change(screen.getByRole('combobox', { name: 'JSON 列' }), { target: { value: 'j' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'JSON 路径' }), { target: { value: '$.' + key } });
  fireEvent.click(screen.getByRole('button', { name: '检查键' }));
  return { mock, receipt: within(await screen.findByRole('region', { name: '键检查回执' })) };
}

it('opens the one matching source/column read in one click and invalidates the receipt on key edit', async () => {
  const { receipt, mock } = await checkReceipt([original, x]);
  expect(receipt.getByText(/右侧当前显示其他分支/)).toBeVisible();
  fireEvent.click(receipt.getByRole('button', { name: '查看此键的读取证据' }));
  expect(await screen.findByTestId('editor-selection')).toHaveTextContent("'$.a.x'");
  expect(screen.getByRole('heading', { name: 'demo.events · j · $.a.x' })).toBeVisible();
  expect(receipt.getByText(/全部 2 个输出/)).toBeVisible();
  expect(mock).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByText('分析来源与证据下载'));
  expect(screen.getByText(/将下载：键检查证据 · demo.events · j · a · 检查范围/)).toBeVisible();
  fireEvent.click(screen.getByText('高级核查记录'));
  expect(screen.getByText('服务键检查记录')).toBeVisible();
  fireEvent.change(screen.getByRole('textbox', { name: 'JSON 路径' }), { target: { value: 'b' } });
  expect(screen.queryByRole('region', { name: '键检查回执' })).not.toBeInTheDocument();
  expect(screen.queryByTestId('editor-selection')).not.toBeInTheDocument();
  expect(screen.getByText('尚未执行高级核查。')).toBeVisible();
  expect(screen.getByText(/将下载：分析证据/)).toBeVisible();
});

it('lets the user choose among distinct read sites and marks unknown output flow', async () => {
  const call = receiptSql.indexOf('get_json_object(t.j,');
  const secondX = { ...x, json_path_position: undefined, position: { start: call, end: call + 'get_json_object'.length } };
  const { receipt } = await checkReceipt([original, x, x, secondX, y]);
  expect(screen.queryByTestId('editor-selection')).not.toBeInTheDocument();
  expect(receipt.getAllByRole('button', { name: /j · \$\.a\.x/ })).toHaveLength(2);
  const choose = receipt.getByRole('button', { name: /j · \$\.a\.y.*输出流向待确认/ });
  fireEvent.click(choose);
  expect(await screen.findByTestId('editor-selection')).toHaveTextContent("'$.a.y'");
  expect(screen.getByRole('heading', { name: 'demo.events · j · $.a.y' })).toBeVisible();
});

it('explains why a matching path cannot be located and never offers a different column as evidence', async () => {
  const { receipt } = await checkReceipt([original, read('j', '$.a.x', false)], 'UNKNOWN');
  expect(receipt.getByText(/本次没有可定位的读取证据.*没有有效的 SQL 位置/)).toBeVisible();
  expect(receipt.queryByRole('button', { name: /读取证据/ })).not.toBeInTheDocument();
  expect(receipt.getByText('暂不能判断')).toBeVisible();
  expect(screen.queryByTestId('editor-selection')).not.toBeInTheDocument();
});

it('keeps SELECT and WHERE positions navigable without attributing aggregate path outputs to either site', async () => {
  const sql = "SELECT get_json_object(t.j, '$.sku') AS x FROM demo.events t\r\n"
    + "WHERE get_json_object(t.j, '$.sku') = 'sample'";
  const literal = "'$.sku'";
  const projection = { ...x, path: '$.sku', path_tokens: [{ kind: 'key', value: 'sku' }] };
  const sites = [['SELECT', 'VALUE', sql.indexOf(literal)], ['WHERE', 'CONDITION', sql.lastIndexOf(literal)]] as const;
  const { receipt, mock } = await checkReceipt(sites.map(([clause, role, start]) => ({
    ...projection, clause, role, json_path_position: { start, end: start + literal.length },
  })), 'UNKNOWN', sql, 'sku', projection);
  const buttons = receipt.getAllByRole('button', { name: /j · \$\.sku/ });
  expect(buttons).toHaveLength(2);
  for (const button of buttons) {
    expect(button).toHaveTextContent('输出流向待确认');
    expect(button).not.toHaveTextContent('x（语句');
  }
  expect(screen.getByText(/^路径流向概览：/)).toHaveTextContent('x（语句');
  fireEvent.click(receipt.getByRole('button', { name: /SELECT.*第 1 行/ }));
  expect(await screen.findByTestId('editor-selection')).toHaveTextContent("1:29 '$.sku'");
  fireEvent.click(receipt.getByRole('button', { name: /WHERE.*第 2 行/ }));
  expect(await screen.findByTestId('editor-selection')).toHaveTextContent("2:28 '$.sku'");
  expect(receipt.getByText('暂不能判断')).toBeVisible();
  expect(mock).toHaveBeenCalledTimes(2);
});
