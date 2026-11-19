import { fireEvent, render, screen, within } from '@testing-library/react';
import { createHash } from 'node:crypto';
import { afterEach, expect, it, vi } from 'vitest';
import { analyzeSubfieldSql } from '../api/client';
import type { Position } from './contract';
import type { createSQLPositionIndex } from './sqlPositionIndex';
import fixture from './p1-proof.fixture.json';
import SubfieldWorkbench from './SubfieldWorkbench';

vi.mock('../api/client', () => ({ analyzeSubfieldSql: vi.fn() }));
vi.mock('./SubfieldEditor', () => ({ default: ({ sql, setSql, locate, positionIndex }: {
  sql: string; setSql: (value: string) => void; locate: Position | null;
  positionIndex: ReturnType<typeof createSQLPositionIndex> | null;
}) => <><textarea aria-label="输入 SQL" value={sql} onChange={e => setSql(e.target.value)} />
  {locate && <output data-testid="sql-anchor">{positionIndex?.excerpt(locate)?.match}</output>}</> }));
afterEach(() => { vi.mocked(analyzeSubfieldSql).mockReset(); vi.unstubAllGlobals(); });

async function analyze() {
  vi.stubGlobal('crypto', { subtle: { digest: async (_: string, bytes: Uint8Array) =>
    Uint8Array.from(createHash('sha256').update(bytes).digest()).buffer } });
  const mock = vi.mocked(analyzeSubfieldSql).mockResolvedValueOnce(fixture.analysis);
  render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '编辑 SQL 原文' }));
  fireEvent.change(await screen.findByRole('textbox', { name: '输入 SQL' }), { target: { value: fixture.sql } });
  fireEvent.click(screen.getByRole('button', { name: '分析 SQL' }));
  await screen.findByText(/服务结果 ·/);
  return mock;
}

const key = (value: string) => fireEvent.change(screen.getByRole('textbox', { name: 'JSON 路径' }), { target: { value } });
const check = () => fireEvent.click(screen.getByRole('button', { name: '检查键' }));
const receipt = async () => within(await screen.findByRole('region', { name: '键检查回执' }));

it('locates the verified SELECT and WHERE separately while keeping UNKNOWN; rejects a mismatched proof', async () => {
  const mock = await analyze();
  mock.mockResolvedValueOnce({ ...fixture.analysis, review: fixture.review });
  key('$.a');
  check();
  const panel = await receipt();
  expect(panel.getByText('暂不能判断')).toBeVisible();
  expect(panel.queryByText(/可作为待核查的剪枝候选/)).not.toBeInTheDocument();
  expect(panel.getByText(/SELECT 读取.*\$\.a\.scene.*键.*a/)).toBeVisible();
  fireEvent.click(panel.getByRole('button', { name: '定位 SELECT 读取函数' }));
  expect(await screen.findByTestId('sql-anchor')).toHaveTextContent(/^get_json_object$/);
  fireEvent.click(panel.getByRole('button', { name: '定位 WHERE 谓词' }));
  expect(await screen.findByTestId('sql-anchor')).toHaveTextContent(/^t\.enabled = 'yes'$/);
  expect(mock).toHaveBeenCalledTimes(2);
  key('$.absent');
  expect(screen.queryByTestId('sql-anchor')).not.toBeInTheDocument();
  mock.mockResolvedValueOnce({ ...fixture.analysis, review: fixture.review });
  check();
  expect((await receipt()).queryByRole('button', { name: '定位 WHERE 谓词' })).not.toBeInTheDocument();
});

it('only explains source case for the exact UNKNOWN key entry, including old reviews without a proof', async () => {
  const mock = await analyze();
  const response = (entries: unknown[]) => ({ ...fixture.analysis, review: { candidate_assessment: {
    status: 'UNKNOWN', entries,
  } } });
  const match = { source: 'toy.events', column: 'payload', key: 'a' };
  const mismatch = 'SOURCE_NAME_CASE_MISMATCH_UNVERIFIED', ambiguous = 'SOURCE_NAME_CASE_AMBIGUOUS';
  const matches = [
    [response([{ ...match, status: 'UNKNOWN', reason: mismatch },
      { ...match, key: 'b', status: 'UNKNOWN', reason: ambiguous }]), '源名大小写与已观测的拼写不同'],
    [response([{ ...match, status: 'UNKNOWN', reason: ambiguous }]), 'SQL 中存在多个仅大小写不同的源名'],
  ] as const;
  key('$.a');
  for (const [raw, message] of matches) {
    mock.mockResolvedValueOnce(raw);
    check();
    const panel = await receipt();
    expect(panel.getByText(new RegExp(message))).toBeVisible();
    expect(panel.queryByRole('button', { name: '定位 WHERE 谓词' })).not.toBeInTheDocument();
  }
  mock.mockResolvedValueOnce(response([{ ...match, status: 'OBSERVED', reason: mismatch }]));
  check();
  const panel = await receipt();
  expect(panel.getByText('已看到读取')).toBeVisible();
  expect(panel.queryByText(/尚未确认是否同一数据源/)).not.toBeInTheDocument();
});
