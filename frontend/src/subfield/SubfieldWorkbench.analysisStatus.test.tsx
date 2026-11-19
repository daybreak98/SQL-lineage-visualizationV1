import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { analyzeSubfieldSql } from '../api/client';
import SubfieldWorkbench from './SubfieldWorkbench';
import { keyCheck, keyCheckReason } from './taskSummary';

vi.mock('../api/client', () => ({ analyzeSubfieldSql: vi.fn() }));
afterEach(() => vi.mocked(analyzeSubfieldSql).mockReset());

const source = { source: 'src', column: 'j', path: '$.a', path_tokens: [{ kind: 'key', value: 'a' }] };
const data = { uses: [{ ...source, kind: 'EXTRACT', role: 'VALUE' }],
  mappings: [{ root: true, output: 'hit', statement: 1, scope: '1:1', slot: 1, inputs: [source] }],
  unknowns: [] };
const key = { source: 'src', column: 'j', key: 'b' };

it('keeps partial facts, selected output proof and the explicit key decision independent', async () => {
  const incomplete = { ...data, coverage: { parsed: true, analysis_status: 'ANALYSIS_INCOMPLETE' },
    opaque_call_arguments: [{ operation: 'OPAQUE_CALL_ARGUMENT' }],
    unknowns: [{ code: 'UNSUPPORTED_JSON_PATH' }, { code: 'UNBOUND_COLUMN' }] };
  const mock = vi.mocked(analyzeSubfieldSql).mockResolvedValueOnce(incomplete)
    .mockResolvedValueOnce({ ...incomplete, review: { path_demand_status: 'ANALYSIS_INCOMPLETE',
      candidate_assessment: { entries: [], reason: 'ANALYSIS_INCOMPLETE' } } })
    .mockResolvedValueOnce({ ...data, coverage: { parsed: true, analysis_status: 'JSON_USE_OBSERVED' } })
    .mockResolvedValueOnce({ ...data, review: { path_demand_status: 'OBSERVED',
      candidate_assessment: { entries: [{ ...key, status: 'NOT_OBSERVED_NEEDS_VALIDATION' }] } } });
  render(<SubfieldWorkbench />);
  const tryExample = () => fireEvent.click(screen.getByRole('button', { name: '试用示例' }));
  const summary = () => within(screen.getByRole('region', { name: '本次核查结论' }));
  const check = () => {
    fireEvent.change(screen.getByRole('textbox', { name: 'JSON 路径' }), { target: { value: '$.b' } });
    fireEvent.click(screen.getByRole('button', { name: '检查键' }));
  };
  tryExample();
  expect(await screen.findByText(/已看到部分证据，但分析尚未完成/)).toBeVisible();
  expect(summary().getByText(/动态.*路径.*未绑定.*不透明/)).toBeVisible();
  expect(summary().getByText('1 条 JSON 路径')).toBeVisible();
  expect(summary().queryByText(/所选输出：普通路径证明未完成/)).not.toBeInTheDocument();
  check();
  expect(await summary().findByText('所选输出：普通路径证明未完成')).toBeVisible();
  expect(summary().getByText('暂不能判断')).toBeVisible();
  expect(summary().queryByText(/可作为待核查的剪枝候选/)).not.toBeInTheDocument();
  tryExample();
  expect(await screen.findByText(/已观察到 JSON 读取/)).toBeVisible();
  expect(summary().queryByText('所选输出：普通路径证明未完成')).not.toBeInTheDocument();
  check();
  expect(await summary().findByText(/每个所选输出均已取得普通路径读取证据/)).toBeVisible();
  expect(summary().getByText('本次未见读取')).toBeVisible();
  expect(summary().getByText(/可作为待核查的剪枝候选/)).toBeVisible();
  expect(mock).toHaveBeenCalledTimes(4);
});

it.each([
  ['NO_ANALYZABLE_SQL', '没有可分析的 SQL 语句'],
  ['NO_JSON_USE_IN_SCOPE', '本次可确认的 SQL 范围内没有显式 JSON 操作'],
  [undefined, '暂未取得可确认的证据'],
])('handles empty analysis without inferring a key outcome (%s)', async (analysis_status, label) => {
  vi.mocked(analyzeSubfieldSql).mockResolvedValue({ uses: [], mappings: [], unknowns: [],
    coverage: { parsed: true, analysis_status } });
  render(<SubfieldWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '试用示例' }));
  expect(await screen.findByText(label)).toBeVisible();
  expect(screen.queryByText('本次未见读取')).not.toBeInTheDocument();
});

it('explains incomplete output coverage without discarding observed key results', () => {
  const reason = 'PROJECTION_SCOPE_NOT_CLOSED';
  const observed = { ...key, key: 'a' };
  const entries = [{ ...key, status: 'UNKNOWN', reason }, { ...observed, status: 'OBSERVED' }];
  const review = { candidate_assessment: { entries, reason } };
  expect(keyCheck(review, observed)).toBe('observed');
  expect(keyCheck(review, key)).toBe('unknown');
  expect(keyCheckReason(review, [], key)).toBe('所检查的 SQL 中，有输出项尚未完成解析，暂不能判断此键是否未被读取。');
  expect(keyCheckReason({ candidate_assessment: { entries: [] } }, [], key)).toBeUndefined();
});
