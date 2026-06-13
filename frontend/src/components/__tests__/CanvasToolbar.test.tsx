import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CanvasToolbar } from '../CanvasToolbar';
import type { WorkbenchState } from '../../types/lineage';

function baseState(overrides: Partial<WorkbenchState> = {}): WorkbenchState {
  return {
    pageMode: 'analyzed',
    analysisStatus: 'success',
    trustStatus: 'trusted',
    selectedOutput: null,
    selectedEntity: 'out:group',
    selectedMapping: null,
    renderMode: 'subquery_dependency',
    graphViewMode: 'subquery',
    detailMode: 'collapsed',
    detailTab: 'summary',
    drawerOpen: false,
    drawerTab: 'diagnostics',
    split: 28,
    query: '',
    scope: 'all',
    large: false,
    positions: {},
    ...overrides,
  };
}

describe('CanvasToolbar', () => {
  it('issues canvas commands for fit, center, and reset viewport controls', () => {
    const setState = vi.fn();
    render(<CanvasToolbar state={baseState()} setState={setState} onTransition={vi.fn()} />);

    fireEvent.click(screen.getByText('Fit Path'));
    fireEvent.click(screen.getByText('Center'));
    fireEvent.click(screen.getByText('Reset Viewport'));

    const nextStates = setState.mock.calls.map(([updater]) => updater(baseState()));
    expect(nextStates.map((state) => state.canvasCommand?.type)).toEqual(['fit', 'center', 'reset']);
    expect(nextStates[2].positions).toEqual({});
  });

  it('disables focus until an output field is selected', () => {
    const { rerender } = render(<CanvasToolbar state={baseState()} setState={vi.fn()} onTransition={vi.fn()} />);

    expect(screen.getByText('Focus')).toBeDisabled();

    rerender(<CanvasToolbar state={baseState({ selectedOutput: 'output_column:order_cnt' })} setState={vi.fn()} onTransition={vi.fn()} />);

    expect(screen.getByText('Focus')).not.toBeDisabled();
  });

  it('disables clear until there is an active selection', () => {
    const { rerender } = render(<CanvasToolbar state={baseState()} setState={vi.fn()} onTransition={vi.fn()} />);

    expect(screen.getByText('Clear')).toBeDisabled();

    rerender(<CanvasToolbar state={baseState({ selectedEntity: 'table:dwd_order_di' })} setState={vi.fn()} onTransition={vi.fn()} />);

    expect(screen.getByText('Clear')).not.toBeDisabled();
  });
});
