import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { LineageCanvas } from '../LineageCanvas';
import type { WorkbenchState } from '../../types/lineage';
import { subqueryEdges, subqueryNodes } from '../../data/mockLineage';

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
    backendGraph: { nodes: subqueryNodes, edges: subqueryEdges },
    ...overrides,
  };
}

describe('LineageCanvas', () => {
  it('renders table and output graph nodes in table view mode', () => {
    const state = baseState(); // defaults to graphViewMode: 'table'
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    // In table view, only table and output type nodes are visible
    const tableNodes = subqueryNodes.filter(n => n.type === 'table' || n.type === 'output');
    for (const node of tableNodes) {
      const el = screen.getByText(node.label, { selector: '.title' });
      expect(el).toBeInTheDocument();
    }
    // CTE and subquery nodes should NOT be visible in table view
    const cteNodes = subqueryNodes.filter(n => n.type === 'cte' || n.type === 'subquery');
    for (const node of cteNodes) {
      expect(screen.queryByText(node.label, { selector: '.title' })).toBeNull();
    }
  });

  it('shows message when not analyzed', () => {
    const notAnalyzed = baseState({ pageMode: 'empty', trustStatus: 'untrusted' });
    const setState = vi.fn();
    render(<LineageCanvas state={notAnalyzed} setState={setState} />);

    const message = screen.getByText(/Paste SQL or load example/i);
    expect(message).toBeInTheDocument();
  });

  it('shows analysis failed message when pageMode is failed', () => {
    const failed = baseState({ pageMode: 'failed', trustStatus: 'untrusted' });
    const setState = vi.fn();
    render(<LineageCanvas state={failed} setState={setState} />);

    const message = screen.getByText(/Analysis failed/i);
    expect(message).toBeInTheDocument();
  });

  it('shows zoom controls', () => {
    const state = baseState();
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    // Zoom buttons: -, +, Reset, and percentage display
    const zoomOut = screen.getByText('-');
    const zoomIn = screen.getByText('+');
    const reset = screen.getByText('Reset');
    const percentage = screen.getByText(/125%|100%/);

    expect(zoomOut).toBeInTheDocument();
    expect(zoomIn).toBeInTheDocument();
    expect(reset).toBeInTheDocument();
    expect(percentage).toBeInTheDocument();
  });

  it('supports node click to select entity', () => {
    const state = baseState();
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    const firstVisible = subqueryNodes.filter(n => n.type === 'table' || n.type === 'output')[0];
    const firstNode = screen.getByText(firstVisible.label, { selector: '.title' });
    fireEvent.click(firstNode);

    expect(setState).toHaveBeenCalled();
    const updater = setState.mock.calls[0][0] as (s: WorkbenchState) => WorkbenchState;
    const newState = updater(state);
    expect(newState.selectedEntity).toBe(firstVisible.entityId);
    expect(newState.detailMode).toBe('compact');
  });

  it('shows no message when fully analyzed and trusted', () => {
    const state = baseState({ pageMode: 'analyzed', trustStatus: 'trusted' });
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    // The message div with class "message" should NOT be rendered
    const messageEl = document.querySelector('.viewport .message');
    expect(messageEl).toBeNull();
  });

  it('renders SVG edge layer with marker definitions', () => {
    const state = baseState();
    const setState = vi.fn();
    const { container } = render(<LineageCanvas state={state} setState={setState} />);

    const svg = container.querySelector('svg.edge-layer');
    expect(svg).toBeInTheDocument();

    // Marker definitions for arrows
    const arrowDefault = container.querySelector('#arrowDefault');
    const arrowPrimary = container.querySelector('#arrowPrimary');
    expect(arrowDefault).toBeInTheDocument();
    expect(arrowPrimary).toBeInTheDocument();
    expect(arrowDefault).toHaveAttribute('markerWidth', '6.3');
    expect(arrowDefault).toHaveAttribute('markerHeight', '6.3');
    expect(arrowPrimary).toHaveAttribute('markerWidth', '6.3');
    expect(arrowPrimary).toHaveAttribute('markerHeight', '6.3');
  });

  it('does not render default lineage nodes without backendGraph', () => {
    const state = baseState({ backendGraph: undefined, positions: {} });
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    expect(screen.queryByText('dwd_order_di', { selector: '.title' })).toBeNull();
    expect(screen.queryByText('Output Group', { selector: '.title' })).toBeNull();
  });

  it('does not render edge text labels', () => {
    const state = baseState();
    const setState = vi.fn();
    const { container } = render(<LineageCanvas state={state} setState={setState} />);

    expect(container.querySelector('.edge-label')).toBeNull();
  });

  it('supports wheel zoom without page scroll', () => {
    const state = baseState();
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    const viewport = document.querySelector('.viewport') as HTMLElement;
    fireEvent.wheel(viewport, { deltaY: -120, clientX: 120, clientY: 120 });

    expect(screen.getByText(/138%/)).toBeInTheDocument();
  });

  it('supports panning the canvas from empty space', () => {
    const state = baseState();
    const setState = vi.fn();
    const { container } = render(<LineageCanvas state={state} setState={setState} />);

    const viewport = container.querySelector('.viewport') as HTMLElement;
    fireEvent.mouseDown(viewport, { button: 0, clientX: 100, clientY: 100 });
    fireEvent.mouseMove(viewport, { clientX: 140, clientY: 130 });
    const transform = container.querySelector('.canvas-transform') as HTMLElement;

    expect(transform.style.transform).toContain('translate(40px, 30px)');
  });

  it('positions graph nodes at the same coordinates used by edges', () => {
    const state = baseState();
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    const title = screen.getByText('dwd_order_di', { selector: '.title' });
    const node = title.closest('.node');

    expect(node).toHaveStyle({
      left: '80px',
      top: '72px',
    });
  });

  it('displays GraphRenderMode stats section', () => {
    const state = baseState();
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    const statsTitle = screen.getByText('GraphRenderMode');
    expect(statsTitle).toBeInTheDocument();
  });
});
