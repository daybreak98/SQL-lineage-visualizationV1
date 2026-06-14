import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DetailPanel } from '../DetailPanel';
import type { WorkbenchState } from '../../types/lineage';
import { subqueryEdges, subqueryNodes } from '../../data/mockLineage';

function baseState(overrides: Partial<WorkbenchState> = {}): WorkbenchState {
  return {
    pageMode: 'analyzed',
    analysisStatus: 'success',
    trustStatus: 'trusted',
    selectedOutput: null,
    selectedEntity: 'physical_table:dwd_order_di',
    selectedMapping: null,
    renderMode: 'subquery_dependency',
    graphViewMode: 'table',
    detailMode: 'compact',
    detailTab: 'summary',
    drawerOpen: false,
    drawerTab: 'diagnostics',
    split: 28,
    query: '',
    scope: 'all',
    large: false,
    positions: {},
    backendGraph: { nodes: subqueryNodes, edges: subqueryEdges },
    ...overrides,
  };
}

describe('DetailPanel', () => {
  it('closes the bottom detail panel when Close is clicked', () => {
    const state = baseState();
    const setState = vi.fn();

    render(<DetailPanel state={state} setState={setState} />);

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    expect(setState).toHaveBeenCalled();
    const updater = setState.mock.calls[0][0] as (s: WorkbenchState) => WorkbenchState;
    expect(updater(state).detailMode).toBe('collapsed');
  });
});
