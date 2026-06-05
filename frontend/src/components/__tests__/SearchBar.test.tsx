import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SearchBar } from '../SearchBar';
import type { SearchItem, WorkbenchState } from '../../types/lineage';

const backendSearchItems: SearchItem[] = [
  {
    itemId: 'search-output-order-cnt',
    entityId: 'out:order_cnt',
    displayName: 'order_cnt',
    type: 'output',
    sub: 'count(order_no)',
    reason: 'backend graph',
    confidence: 'high',
  },
  {
    itemId: 'search-source-order',
    entityId: 'physical_table:dwd_order_di',
    displayName: 'dwd_order_di',
    type: 'source',
    sub: 'table',
    reason: 'backend graph',
    confidence: 'high',
  },
];

function baseState(overrides: Partial<WorkbenchState> = {}): WorkbenchState {
  return {
    pageMode: 'analyzed',
    analysisStatus: 'success',
    trustStatus: 'trusted',
    selectedOutput: null,
    selectedEntity: 'out:group',
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
    backendSearchItems,
    ...overrides,
  };
}

const onSelectResult = vi.fn();

describe('SearchBar', () => {
  it('shows search results popover when focused and analyzed', () => {
    const state = baseState();
    const setState = vi.fn();
    render(<SearchBar state={state} setState={setState} onSelectResult={onSelectResult} />);

    const input = screen.getByPlaceholderText(/Search field/i);
    fireEvent.focus(input);

    // Popover should be visible with results
    const popover = document.querySelector('.popover.open');
    expect(popover).toBeInTheDocument();
  });

  it('disables search input when not analyzed', () => {
    const state = baseState({ pageMode: 'empty', trustStatus: 'untrusted' });
    const setState = vi.fn();
    render(<SearchBar state={state} setState={setState} onSelectResult={onSelectResult} />);

    const input = screen.getByPlaceholderText(/Search field/i);
    expect(input).toBeDisabled();
  });

  it('disables scope select when not analyzed', () => {
    const state = baseState({ pageMode: 'empty', trustStatus: 'untrusted' });
    const setState = vi.fn();
    render(<SearchBar state={state} setState={setState} onSelectResult={onSelectResult} />);

    const select = document.querySelector('select.select');
    expect(select).toBeDisabled();
  });

  it('shows output capsule with path status', () => {
    const state = baseState();
    const setState = vi.fn();
    render(<SearchBar state={state} setState={setState} onSelectResult={onSelectResult} />);

    // Output capsule shows idle status when no output selected
    const capsule = document.querySelector('.output-capsule');
    expect(capsule).toBeInTheDocument();

    const nameEl = capsule?.querySelector('.name');
    expect(nameEl?.textContent).toBe('Choose output');
  });

  it('shows output capsule with selected output name', () => {
    const state = baseState({ selectedOutput: 'out:order_cnt' });
    const setState = vi.fn();
    render(<SearchBar state={state} setState={setState} onSelectResult={onSelectResult} />);

    const nameEl = document.querySelector('.output-capsule .name');
    expect(nameEl?.textContent).toBe('order_cnt');
  });

  it('shows stale pill when trustStatus is stale', () => {
    const state = baseState({ trustStatus: 'stale' });
    const setState = vi.fn();
    render(<SearchBar state={state} setState={setState} onSelectResult={onSelectResult} />);

    const pill = screen.getByText('stale');
    expect(pill).toBeInTheDocument();
  });

  it('shows trusted results count pill when trusted', () => {
    const state = baseState({ trustStatus: 'trusted' });
    const setState = vi.fn();
    render(<SearchBar state={state} setState={setState} onSelectResult={onSelectResult} />);

    const pill = screen.getByText(/results$/);
    expect(pill).toBeInTheDocument();
  });

  it('clears query when clear button is clicked', () => {
    const state = baseState({ query: 'test' });
    const setState = vi.fn();
    render(<SearchBar state={state} setState={setState} onSelectResult={onSelectResult} />);

    const clearBtn = screen.getByText('Clear');
    fireEvent.click(clearBtn);

    expect(setState).toHaveBeenCalled();
  });

  it('calls onSelectResult when a search result is clicked', () => {
    const state = baseState();
    const setState = vi.fn();
    const onSelect = vi.fn();
    render(<SearchBar state={state} setState={setState} onSelectResult={onSelect} />);

    const input = screen.getByPlaceholderText(/Search field/i);
    fireEvent.focus(input);

    // Find the first result button in the popover
    const resultButtons = document.querySelectorAll('.popover .result');
    expect(resultButtons.length).toBeGreaterThan(0);

    fireEvent.click(resultButtons[0]);
    expect(onSelect).toHaveBeenCalled();
  });

  it('shows empty state when backend returned no searchable items', () => {
    const state = baseState({ backendSearchItems: [] });
    const setState = vi.fn();
    render(<SearchBar state={state} setState={setState} onSelectResult={onSelectResult} />);

    const input = screen.getByPlaceholderText(/Search field/i);
    fireEvent.focus(input);

    expect(screen.getByText('No backend search results for the current analysis.')).toBeInTheDocument();
  });

  it('renders scope select with all options', () => {
    const state = baseState();
    const setState = vi.fn();
    render(<SearchBar state={state} setState={setState} onSelectResult={onSelectResult} />);

    const select = document.querySelector('select.select');
    expect(select).toBeInTheDocument();

    const options = select?.querySelectorAll('option');
    const optionValues = Array.from(options ?? []).map((o) => o.value);
    expect(optionValues).toContain('all');
    expect(optionValues).toContain('output');
    expect(optionValues).toContain('source');
    expect(optionValues).toContain('cte');
    expect(optionValues).toContain('subquery');
    expect(optionValues).toContain('expression');
  });
});
