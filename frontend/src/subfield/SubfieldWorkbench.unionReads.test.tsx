import { fireEvent, render, screen, within } from '@testing-library/react';
import { createHash } from 'node:crypto';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';
import { analyzeSubfieldSql } from '../api/client';
import type { Position } from './contract';
import type { createSQLPositionIndex } from './sqlPositionIndex';
import fixture from './union-output-reads.fixture.json';
import SubfieldWorkbench from './SubfieldWorkbench';

vi.mock('../api/client', () => ({ analyzeSubfieldSql: vi.fn() }));
vi.mock('./SubfieldEditor', () => ({ default: ({ sql, setSql, locate, positionIndex }: {
  sql: string; setSql: (text: string) => void; locate: Position | null;
  positionIndex: ReturnType<typeof createSQLPositionIndex> | null;
}) => <><textarea aria-label="输入 SQL" value={sql} onChange={e => setSql(e.target.value)} />
  {locate && positionIndex && <output data-testid="sql-anchor">
    {positionIndex.lineAt(locate.start)}:{positionIndex.excerpt(locate)?.match}
  </output>}</> }));
const originalScroll = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollIntoView');
beforeAll(() => Object.defineProperty(Element.prototype, 'scrollIntoView', { configurable: true, value: vi.fn() }));
afterAll(() => {
  if (originalScroll) Object.defineProperty(Element.prototype, 'scrollIntoView', originalScroll);
  else Reflect.deleteProperty(Element.prototype, 'scrollIntoView');
});
afterEach(() => { vi.mocked(analyzeSubfieldSql).mockReset(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function analyze(response: unknown, sql = fixture.sql, dialect = 'spark') {
  vi.stubGlobal('crypto', { subtle: { digest: async (_: string, bytes: Uint8Array) =>
    Uint8Array.from(createHash('sha256').update(bytes).digest()).buffer } });
  const mock = vi.mocked(analyzeSubfieldSql).mockResolvedValue(response);
  render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '编辑 SQL 原文' }));
  fireEvent.change(screen.getByRole('combobox', { name: '方言' }), { target: { value: dialect } });
  fireEvent.change(await screen.findByRole('textbox', { name: '输入 SQL' }), { target: { value: sql } });
  fireEvent.click(screen.getByRole('button', { name: '分析 SQL' }));
  await screen.findByText(/服务结果 ·/);
  return mock;
}

it('locates the virtual producer’s SELECT and WHERE occurrences without assigning WHERE to the output', async () => {
  const mock = await analyze(fixture.analysis);
  const locator = await screen.findByText('联合输出槽读取');
  fireEvent.click(locator);
  const select = screen.getByRole('button', { name: /^SELECT.*1:3/ });
  fireEvent.click(select);
  expect(screen.getByText(/源分支类型转换未核验/)).toBeVisible();
  let evidence = within(screen.getByRole('region', { name: '当前联合输出槽证据' }));
  expect(evidence.getByText(/消费输出.*1:4/)).toBeVisible();
  fireEvent.click(evidence.getByRole('button', { name: '定位 JSON 路径字面量' }));
  expect(await screen.findByTestId('sql-anchor')).toHaveTextContent("1:'$.k'");
  fireEvent.click(screen.getByRole('button', { name: /^WHERE.*1:3/ }));
  evidence = within(screen.getByRole('region', { name: '当前联合输出槽证据' }));
  expect(evidence.getByText(/条件读取，没有消费输出槽/)).toBeVisible();
  expect(evidence.queryByText(/消费输出.*1:4/)).not.toBeInTheDocument();
  fireEvent.click(evidence.getByRole('button', { name: '定位 JSON 路径字面量' }));
  expect(screen.getByTestId('sql-anchor')).toHaveTextContent("3:'$.k'");
  fireEvent.click(screen.getByText('其他分析记录'));
  fireEvent.click(screen.getByText(/传播映射 ·/));
  fireEvent.click(await screen.findByRole('button', { name: /^hit · 语句 1 \/ 作用域 1:4/ }));
  expect(screen.getByRole('button', { name: /^SELECT.*1:3/ })).toBeVisible();
  expect(screen.queryByRole('button', { name: /^WHERE.*1:3/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '查看全部联合消费点' }));
  expect(screen.getByRole('button', { name: /^WHERE.*1:3/ })).toBeVisible();
  expect(mock).toHaveBeenCalledTimes(1);
});

it('leaves old responses unchanged and ignores proof with a mismatched SQL identity', async () => {
  const { union_output_reads: reads, ...old } = fixture.analysis;
  const mock = await analyze(old);
  expect(screen.queryByText('联合输出槽读取')).not.toBeInTheDocument();
  mock.mockResolvedValueOnce({ ...old, union_output_reads: reads, coverage: { ...old.coverage, sql_sha256: 'mismatch' } });
  fireEvent.click(screen.getByRole('button', { name: '分析 SQL' }));
  await screen.findByText(/服务结果 ·/);
  expect(screen.queryByText('联合输出槽读取')).not.toBeInTheDocument();
});

it('isolates the unverified derived path while retaining an independent in-branch read', async () => {
  const { default: { analysis, sql } } = await import('./union-unverified.fixture.json');
  const mock = await analyze(analysis, sql);
  const tree = within(screen.getByRole('region', { name: 'JSON 枝干树' }));
  expect(tree.getByRole('button', { name: /local_key.*已看到读取/ })).toBeVisible();
  expect(tree.queryByRole('button', { name: /wrapped/ })).not.toBeInTheDocument();
  expect(screen.getByText(/集合类型转换未核验.*不计为物理读取/)).toBeVisible();
  expect(await screen.findByText('联合输出槽读取')).toBeVisible();
  const search = screen.getByRole('searchbox');
  fireEvent.change(search, { target: { value: '$.wrapped' } });
  expect(screen.getByText('未找到匹配路径')).toBeVisible();
  expect(mock).toHaveBeenCalledTimes(1);
});

it('shows CASE guards for their exact projection and in the all-sites view without creating a value consumer', async () => {
  const { default: { analysis, sql } } = await import('./union-case-guard.fixture.json');
  const mock = await analyze(analysis, sql, 'hive');
  await screen.findByText('联合输出槽读取');
  fireEvent.click(screen.getByText('其他分析记录'));
  fireEvent.click(screen.getByText(/传播映射 ·/));
  fireEvent.click(await screen.findByRole('button', { name: /^hit · 语句 1 \/ 作用域 1:6 \/ 槽位 1$/ }));
  const guard = within(screen.getByText('联合输出槽读取').closest('details')!).getByRole('button', { name: /^SELECT CASE 条件.*1:5/ });
  fireEvent.click(guard);
  const proof = within(screen.getByRole('region', { name: '当前联合输出槽证据' }));
  expect(proof.getByText(/CASE 投影.*1:6.*槽位 1.*不计入值来源/)).toBeVisible();
  expect(proof.queryByText(/消费输出：/)).not.toBeInTheDocument();
  fireEvent.click(proof.getByRole('button', { name: '定位读取列' }));
  expect(await screen.findByTestId('sql-anchor')).toHaveTextContent('1:packet');
  fireEvent.click(proof.getByRole('button', { name: '定位 JSON 路径字面量' }));
  expect(screen.getByTestId('sql-anchor')).toHaveTextContent("1:'$.kind'");

  fireEvent.click(screen.getByRole('button', { name: /^marker · 语句 1 \/ 作用域 1:6 \/ 槽位 2$/ }));
  const other = within(screen.getByText('联合输出槽读取').closest('details')!);
  expect(other.queryByRole('button', { name: /^SELECT CASE 条件/ })).not.toBeInTheDocument();
  fireEvent.click(other.getByRole('button', { name: '查看全部联合消费点' }));
  expect(other.getByRole('button', { name: /^SELECT CASE 条件.*1:5/ })).toBeVisible();
  expect(mock).toHaveBeenCalledTimes(1);
});

it('keeps visible JOIN reads and offers only diagnostic location for a forward ON reference', async () => {
  const { default: { analysis, sql, review } } = await import('./join-visibility.fixture.json');
  const mock = await analyze(analysis, sql);
  const tree = within(screen.getByRole('region', { name: 'JSON 枝干树' }));
  expect(tree.getByRole('button', { name: /on_ok.*已看到读取/ })).toBeVisible();
  expect(tree.queryByRole('button', { name: /impossible/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByText('JOIN ON 来源未核验'));
  const diagnostics = within(screen.getByRole('region', { name: 'JOIN ON 来源诊断' }));
  expect(diagnostics.getByText(/无法确认.*可见.*不计为物理读取/)).toBeVisible();
  fireEvent.click(diagnostics.getByRole('button', { name: /定位未证 JOIN ON/ }));
  expect(await screen.findByTestId('sql-anchor')).toHaveTextContent("2:'$.impossible'");
  expect(diagnostics.queryByText(/toy\.t/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('textbox', { name: 'JSON 路径' }), { target: { value: '$.impossible' } });
  mock.mockResolvedValueOnce({ ...analysis, review });
  fireEvent.click(screen.getByRole('button', { name: '检查键' }));
  const receipt = within(await screen.findByRole('region', { name: '键检查回执' }));
  expect(receipt.getByText('暂不能判断')).toBeVisible();
  expect(receipt.queryByRole('button', { name: '查看此键的读取证据' })).not.toBeInTheDocument();
});
