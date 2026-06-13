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

  it('supports node double-click to select entity', () => {
    const state = baseState();
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    const firstVisible = subqueryNodes.filter(n => n.type === 'table' || n.type === 'output')[0];
    const firstNode = screen.getByText(firstVisible.label, { selector: '.title' });
    fireEvent.dblClick(firstNode);

    expect(setState).toHaveBeenCalled();
    const updater = setState.mock.calls[0][0] as (s: WorkbenchState) => WorkbenchState;
    const newState = updater(state);
    expect(newState.selectedEntity).toBe(firstVisible.entityId);
    expect(newState.detailMode).toBe('compact');
  });

  it('uses a fast custom full-label tooltip without the left strip', () => {
    const state = baseState();
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    const title = screen.getByText('dwd_order_di', { selector: '.title' });
    const node = title.closest('.node') as HTMLElement;

    expect(node).toHaveAttribute('data-full-label', 'dwd_order_di');
    expect(title).not.toHaveAttribute('title');
    expect(node.querySelector('.strip')).toBeNull();
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

    expect(screen.getByText(/110%/)).toBeInTheDocument();
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
    const node = title.closest('.node') as HTMLElement;
    expect(node).not.toBeNull();
    expect(Number.isFinite(parseFloat(node.style.left))).toBe(true);
    expect(Number.isFinite(parseFloat(node.style.top))).toBe(true);
  });

  it('shows output field edges into Query Result with readable spacing in column view', () => {
    const state = baseState({
      graphViewMode: 'column',
      backendGraph: {
        nodes: [
          { id: 'physical_column:dwd_order_di.order_no', entityId: 'physical_column:dwd_order_di.order_no', type: 'column', label: 'dwd_order_di.order_no', x: 0, y: 0 },
          { id: 'output_column:order_no', entityId: 'output_column:order_no', type: 'output_field', label: 'order_no', x: 0, y: 0 },
          { id: 'query_result:final', entityId: 'query_result:final', type: 'output', label: 'Query Result', x: 0, y: 0 },
        ],
        edges: [
          { id: 'edge:physical_column:dwd_order_di.order_no->output_column:order_no', source: 'physical_column:dwd_order_di.order_no', target: 'output_column:order_no', type: 'projection' },
          { id: 'edge:output_column:order_no->query_result:final', source: 'output_column:order_no', target: 'query_result:final', type: 'output' },
        ],
      },
    });
    const setState = vi.fn();
    const { container } = render(<LineageCanvas state={state} setState={setState} />);

    const outputField = screen.getByText('order_no', { selector: '.title' }).closest('.node') as HTMLElement;
    const queryResult = screen.getByText('Query Result', { selector: '.title' }).closest('.node') as HTMLElement;
    const outputEdge = container.querySelector('path.edge.output');

    expect(outputEdge).toBeInTheDocument();
    expect(parseFloat(queryResult.style.left) - parseFloat(outputField.style.left)).toBeGreaterThan(240);
  });

  it('collapses upstream physical columns into table nodes in column view', () => {
    const state = baseState({
      graphViewMode: 'column',
      backendGraph: {
        nodes: [
          { id: 'physical_table:dwd_order_di', entityId: 'physical_table:dwd_order_di', type: 'table', label: 'dwd_order_di', x: 0, y: 0 },
          { id: 'physical_column:dwd_order_di.order_no', entityId: 'physical_column:dwd_order_di.order_no', type: 'column', label: 'dwd_order_di.order_no', x: 0, y: 0 },
          { id: 'physical_column:dwd_order_di.user_id', entityId: 'physical_column:dwd_order_di.user_id', type: 'column', label: 'dwd_order_di.user_id', x: 0, y: 0 },
          { id: 'output_column:order_no', entityId: 'output_column:order_no', type: 'output_field', label: 'order_no', x: 0, y: 0 },
          { id: 'output_column:uid', entityId: 'output_column:uid', type: 'output_field', label: 'uid', x: 0, y: 0 },
          { id: 'query_result:final', entityId: 'query_result:final', type: 'output', label: 'Query Result', x: 0, y: 0 },
        ],
        edges: [
          { id: 'edge:physical_column:dwd_order_di.order_no->output_column:order_no', source: 'physical_column:dwd_order_di.order_no', target: 'output_column:order_no', type: 'projection' },
          { id: 'edge:output_column:order_no->query_result:final', source: 'output_column:order_no', target: 'query_result:final', type: 'output' },
          { id: 'edge:physical_column:dwd_order_di.user_id->output_column:uid', source: 'physical_column:dwd_order_di.user_id', target: 'output_column:uid', type: 'projection' },
          { id: 'edge:output_column:uid->query_result:final', source: 'output_column:uid', target: 'query_result:final', type: 'output' },
        ],
      },
    });
    const setState = vi.fn();
    const { container } = render(<LineageCanvas state={state} setState={setState} />);

    expect(screen.getByText('dwd_order_di', { selector: '.title' })).toBeInTheDocument();
    expect(screen.queryByText('dwd_order_di.order_no', { selector: '.title' })).not.toBeInTheDocument();
    expect(screen.queryByText('dwd_order_di.user_id', { selector: '.title' })).not.toBeInTheDocument();
    expect(container.querySelectorAll('path.edge.projection')).toHaveLength(2);
  });

  it('displays GraphRenderMode stats section', () => {
    const state = baseState();
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    const statsTitle = screen.getByText('GraphRenderMode');
    expect(statsTitle).toBeInTheDocument();
  });
});
