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
    collapsedRelationIds: {},
    columnContainerMode: 'relation_rows',
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

  it('uses owned toolbar layout classes for the path summary and view controls', () => {
    const { container } = render(<CanvasToolbar state={baseState()} setState={vi.fn()} onTransition={vi.fn()} />);

    expect(container.querySelector('.path-inline')).toBeInTheDocument();
    expect(container.querySelector('.tool-right .view-toggle')).toBeInTheDocument();
    expect(container.querySelector('.flex.items-center.gap-2')).not.toBeInTheDocument();
  });

  it('keeps mature lineage views visible and moves experimental views into a select', () => {
    const setState = vi.fn();
    render(<CanvasToolbar state={baseState()} setState={setState} onTransition={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Subquery' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Table' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Column' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Semantics' })).toBeNull();

    const experimental = screen.getByLabelText('Experimental lineage view');
    expect(experimental).toHaveValue('');

    fireEvent.change(experimental, { target: { value: 'semantics' } });

    const updater = setState.mock.calls[0][0] as (state: WorkbenchState) => WorkbenchState;
    expect(updater(baseState()).graphViewMode).toBe('semantics');
  });

  it('shows the active experimental view in the select', () => {
    render(
      <CanvasToolbar
        state={baseState({ graphViewMode: 'diagnostics' })}
        setState={vi.fn()}
        onTransition={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('Experimental lineage view')).toHaveValue('diagnostics');
  });

  it('does not expose a duplicate diagnostics drawer button beside Focus', () => {
    render(<CanvasToolbar state={baseState()} setState={vi.fn()} onTransition={vi.fn()} />);

    expect(screen.queryByRole('button', { name: 'Diag' })).toBeNull();
    expect(screen.getByLabelText('Experimental lineage view')).toBeInTheDocument();
  });
});
