import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { createHash } from 'node:crypto';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';
import { analyzeSubfieldSql } from '../api/client';
import type { Position } from './contract';
import type { createSQLPositionIndex } from './sqlPositionIndex';
import fixture from './two-step-data01.fixture.json';
import SubfieldWorkbench from './SubfieldWorkbench';

vi.mock('../api/client', () => ({ analyzeSubfieldSql: vi.fn() }));
vi.mock('./SubfieldEditor', () => ({ default: ({ sql, setSql, locate, positionIndex }: {
  sql: string; setSql: (value: string) => void; locate: Position | null;
  positionIndex: ReturnType<typeof createSQLPositionIndex> | null;
}) => <><textarea aria-label="输入 SQL" value={sql} onChange={e => setSql(e.target.value)} />
  {locate && <output data-testid="sql-anchor">{positionIndex?.excerpt(locate)?.match}</output>}</> }));
const originalScroll = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollIntoView');
beforeAll(() => Object.defineProperty(Element.prototype, 'scrollIntoView', { configurable: true, value: vi.fn() }));
afterAll(() => {
  if (originalScroll) Object.defineProperty(Element.prototype, 'scrollIntoView', originalScroll);
  else Reflect.deleteProperty(Element.prototype, 'scrollIntoView');
});
afterEach(() => { vi.mocked(analyzeSubfieldSql).mockReset(); vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function analyze(enabled = true, analysis = fixture.analysis) {
  if (enabled) vi.stubEnv('VITE_SUBFIELD_TWO_STEP_EVIDENCE', '1');
  vi.stubGlobal('crypto', { subtle: { digest: async (_: string, bytes: Uint8Array) =>
    Uint8Array.from(createHash('sha256').update(bytes).digest()).buffer } });
  const mock = vi.mocked(analyzeSubfieldSql).mockResolvedValueOnce(analysis);
  render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '编辑 SQL 原文' }));
  fireEvent.change(await screen.findByRole('textbox', { name: '输入 SQL' }), { target: { value: fixture.sql } });
  fireEvent.click(screen.getByRole('button', { name: '分析 SQL' }));
  await screen.findByText(/服务结果 ·/);
  return mock;
}
function selectOutput(name: 'hit' | 'alt') {
  const path = name === 'hit' ? 'b' : 'z';
  const tree = within(screen.getByRole('region', { name: 'JSON 枝干树' }));
  fireEvent.click(tree.getByRole('button', { name: new RegExp('\\.' + path + '.*' + name) }));
  fireEvent.click(screen.getByRole('button', { name: new RegExp('^' + name + '（语句') }));
}
const requestDetail = () => fireEvent.click(screen.getByRole('button', { name: '查看两步读取' }));
const checkKey = () => fireEvent.click(screen.getByRole('button', { name: '检查键' }));

it('does not render the entry or make extra requests by default', async () => {
  const mock = await analyze(false);
  selectOutput('hit');
  expect(screen.queryByRole('button', { name: '查看两步读取' })).not.toBeInTheDocument();
  expect(mock).toHaveBeenCalledTimes(1);
});

it('uses one root per explicit request, preserves key review and ignores a late former root', async () => {
  const mock = await analyze();
  fireEvent.change(screen.getByRole('textbox', { name: 'JSON 路径' }), { target: { value: '$.a' } });
  mock.mockResolvedValueOnce({ ...fixture.analysis, review: { candidate_assessment: {
    status: 'UNKNOWN', reason: 'PROTECTED_PATH_UNVERIFIED', entries: [],
  } } });
  checkKey();
  const receipt = within(await screen.findByRole('region', { name: '键检查回执' }));
  expect(receipt.getByText(/全部 2 个输出/)).toBeVisible();

  let returnAlt!: (value: unknown) => void;
  mock.mockReturnValueOnce(new Promise(resolve => { returnAlt = resolve; })).mockResolvedValueOnce(fixture.hit);
  selectOutput('alt');
  expect(mock).toHaveBeenCalledTimes(2);
  requestDetail();
  expect(mock).toHaveBeenLastCalledWith({ sql: fixture.sql, dialect: 'spark',
    protected_outputs: [{ statement: 1, scope: '1:2', slot: 2 }], include_two_step_evidence: true });
  selectOutput('hit');
  requestDetail();
  expect(mock).toHaveBeenLastCalledWith({ sql: fixture.sql, dialect: 'spark',
    protected_outputs: [{ statement: 1, scope: '1:2', slot: 1 }], include_two_step_evidence: true });
  const proof = await screen.findByRole('region', { name: '两步读取证据' });
  expect(screen.getByText(/当前只查看输出 hit.*键检查范围和结论不变/)).toBeVisible();
  expect(screen.getByText('当前下载包不包含本次两步详情响应。')).toBeVisible();
  fireEvent.click(screen.getByText('分析来源与证据下载'));
  expect(screen.getByText(/将下载：键检查证据.*检查范围：1\/1:2\/1、1\/1:2\/2/)).toBeVisible();
  expect(within(proof).getAllByRole('listitem').map(row => row.querySelector('p')?.textContent)).toEqual([
    '从来源值提取 a', '从上一步所得值再次提取 b',
  ]);
  await act(async () => returnAlt(fixture.alt));
  expect(screen.getByRole('heading', { name: /输出 hit.*两步读取证据/ })).toBeVisible();
  expect(within(proof).queryByText('z', { selector: 'code' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '定位第 2 步输入列' }));
  expect(await screen.findByTestId('sql-anchor')).toHaveTextContent(/^x$/);
  expect(receipt.getByText('暂不能判断')).toBeVisible();
  expect(receipt.getByText(/全部 2 个输出/)).toBeVisible();
  mock.mockResolvedValueOnce(fixture.alt);
  selectOutput('alt');
  expect(screen.queryByTestId('sql-anchor')).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: '两步读取证据' })).not.toBeInTheDocument();
  requestDetail();
  const alt = await screen.findByRole('region', { name: '两步读取证据' });
  expect(within(alt).getAllByRole('listitem').map(row => row.querySelector('p')?.textContent)).toEqual([
    '从来源值提取 a', '从上一步所得值再次提取 z',
  ]);
  fireEvent.click(within(alt).getByRole('button', { name: '定位第 1 步输入列' }));
  expect(await screen.findByTestId('sql-anchor')).toHaveTextContent(/^j$/);
  fireEvent.change(screen.getByRole('textbox', { name: '输入 SQL' }), { target: { value: fixture.sql + '\n-- changed' } });
  expect(screen.queryByTestId('sql-anchor')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '定位第 2 步输入列' })).not.toBeInTheDocument();
});

it.each([['missing', undefined], ['wrong slot', fixture.alt]])('degrades safely with %s evidence', async (_case, response) => {
  const mock = await analyze();
  mock.mockResolvedValueOnce(response ?? fixture.analysis);
  selectOutput('hit');
  requestDetail();
  expect(await screen.findByText(/本次未提供该输出的两步读取证据.*这不表示未读取/)).toBeVisible();
  expect(screen.queryByRole('button', { name: '定位第 2 步输入列' })).not.toBeInTheDocument();
});

it('shows the two steps but does not offer a jump for an omitted input anchor', async () => {
  const mock = await analyze();
  const detail = structuredClone(fixture.hit);
  Object.assign(detail.review.static_extraction_evidence.source_demand.witness[0].evidence, { position: null });
  mock.mockResolvedValueOnce(detail);
  selectOutput('hit');
  requestDetail();
  const proof = within(await screen.findByRole('region', { name: '两步读取证据' }));
  expect(proof.getByRole('button', { name: '定位第 1 步输入列' })).toBeVisible();
  expect(proof.getByText('本步原文位置未提供。')).toBeVisible();
  expect(proof.queryByRole('button', { name: '定位第 2 步输入列' })).not.toBeInTheDocument();
});

it('can explicitly query an unlinked root but never guesses a repeated port', async () => {
  const mappings = fixture.analysis.mappings.map(row => row.root ? { ...row, inputs: [] } : row);
  const mock = await analyze(true, { ...fixture.analysis, mappings: [...mappings, mappings.find(row => row.output === 'alt')!] });
  const picker = screen.getByRole('combobox', { name: '查看哪个输出的两步读取' });
  expect(screen.queryByRole('button', { name: /^hit（语句/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '查看两步读取' })).not.toBeInTheDocument();
  const hit = within(picker).getByRole('option', { name: /hit.*槽位 1/ }) as HTMLOptionElement;
  expect(within(picker).queryByRole('option', { name: /alt/ })).not.toBeInTheDocument();
  expect(screen.getByText(/部分输出无法唯一识别/)).toBeVisible();
  fireEvent.change(picker, { target: { value: hit.value } });
  expect(mock).toHaveBeenCalledTimes(1);
  mock.mockResolvedValueOnce(fixture.hit);
  requestDetail();
  expect(mock).toHaveBeenLastCalledWith({ sql: fixture.sql, dialect: 'spark',
    protected_outputs: [{ statement: 1, scope: '1:2', slot: 1 }], include_two_step_evidence: true });
  expect(await screen.findByRole('heading', { name: /输出 hit.*两步读取证据/ })).toBeVisible();
});
