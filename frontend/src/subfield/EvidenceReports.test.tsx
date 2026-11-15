import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ReviewSummary } from './EvidenceReports';

it('keeps confirmed branch evidence alongside an unresolved sibling and labels candidate status', async () => {
  const pick = vi.fn();
  const read = { position: { start: 8, end: 13 }, kind: 'COALESCE_INPUT' };
  render(<ReviewSummary pick={pick} value={{
    unknowns: [],
    candidate_assessment: { status: 'NOT_OBSERVED_NEEDS_VALIDATION', entries: [] },
    observed_branch_demands: { by_protected_output: [{
      protected_output: { statement: 1, scope: '1:3', slot: 1 },
      status: 'UNRESOLVED', rowset_verified: false,
      by_source: [{ source: 'src', column: 'j', paths: [{
        path_tokens: [{ kind: 'key', value: 'a' }], reasons: [{ argument_slot: 1, port_reads: [read] }],
      }] }],
      unresolved: [{ argument_slot: 2, reason: 'MISSING_OR_AMBIGUOUS_ARGUMENT' }],
    }] },
  }} />);
  expect(screen.getByText(/值路径已追溯；行集未验证。仍有分支未决/)).toBeInTheDocument();
  expect(screen.getByText(/示例候选键：待验证/)).toBeInTheDocument();
  expect(screen.getByText(/评审未决项：0 项/)).toBeInTheDocument();
  expect(screen.getByText(/已证路径需求（按根输出）：服务未提供/)).toBeInTheDocument();
  for (const label of [/实参值路径 · 1/, /分支未决 · 1/]) {
    const details = screen.getByText(label).closest('details')!;
    details.open = true;
    fireEvent(details, new Event('toggle'));
  }
  fireEvent.click(await screen.findByRole('button', { name: /实参 1 · src · j/ }));
  expect(pick.mock.calls[0][1][0]).toEqual(read);
  expect(screen.getByRole('button', { name: /实参 2 .*MISSING_OR_AMBIGUOUS_ARGUMENT/ })).toBeInTheDocument();
});
