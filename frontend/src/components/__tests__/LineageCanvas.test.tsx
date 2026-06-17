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
    collapsedRelationIds: {},
    columnContainerMode: 'relation_rows',
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

  it('marks downstream nodes and edges as impact targets for the selected node', () => {
    const state = baseState({ graphViewMode: 'subquery', selectedEntity: 'table:dwd_order_di' });
    const setState = vi.fn();
    const { container } = render(<LineageCanvas state={state} setState={setState} />);

    const downstreamNode = screen.getByText('metric_base', { selector: '.title' }).closest('.node') as HTMLElement;
    const unrelatedSourceNode = screen.getByText('dim_user_df', { selector: '.title' }).closest('.node') as HTMLElement;
    const selectedNode = screen.getByText('dwd_order_di', { selector: '.title' }).closest('.node') as HTMLElement;

    expect(selectedNode).not.toHaveAttribute('data-downstream-impact');
    expect(downstreamNode).toHaveAttribute('data-downstream-impact', 'true');
    expect(unrelatedSourceNode).not.toHaveAttribute('data-downstream-impact');
    expect(container.querySelectorAll('path.edge.downstream-impact')).toHaveLength(4);
  });

  it('highlights compressed upstream table edges when output is selected in table view', () => {
    const state = baseState({ graphViewMode: 'table', selectedEntity: 'out:group' });
    const setState = vi.fn();
    const { container } = render(<LineageCanvas state={state} setState={setState} />);

    expect(container.querySelectorAll('path.edge.edge-selected')).toHaveLength(2);
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

  it('resets local pan and zoom when a reset viewport command is received', () => {
    const state = baseState();
    const setState = vi.fn();
    const { container, rerender } = render(<LineageCanvas state={state} setState={setState} />);

    const viewport = container.querySelector('.viewport') as HTMLElement;
    fireEvent.mouseDown(viewport, { button: 0, clientX: 100, clientY: 100 });
    fireEvent.mouseMove(viewport, { clientX: 140, clientY: 130 });
    fireEvent.wheel(viewport, { deltaY: -120, clientX: 120, clientY: 120 });

    const transformedOffset = (container.querySelector('.canvas-transform') as HTMLElement).style.transform;
    expect(transformedOffset).not.toBe('');
    expect(screen.getByText(/110%/)).toBeInTheDocument();

    rerender(<LineageCanvas state={{ ...state, canvasCommand: { type: 'reset', id: 1 } }} setState={setState} />);

    expect((container.querySelector('.canvas-transform') as HTMLElement).style.transform).not.toBe(transformedOffset);
    expect(screen.getByText(/100%/)).toBeInTheDocument();
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

  it('renders column lineage as relation containers with field rows', () => {
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

    const sourceContainer = screen.getByText('dwd_order_di', { selector: '.relation-node__title' }).closest('.relation-node') as HTMLElement;
    const queryResult = screen.getByText('Query Result', { selector: '.relation-node__title' }).closest('.relation-node') as HTMLElement;
    const outputRow = container.querySelector('.column-row[data-role="output"][data-entity-id="output_column\\:order_no"] .column-row__label');
    const projectionEdge = container.querySelector('path.edge.projection');

    expect(sourceContainer).toBeInTheDocument();
    expect(queryResult).toBeInTheDocument();
    expect(outputRow).toBeInTheDocument();
    expect(container.querySelector('.node[data-type="output_field"]')).toBeNull();
    expect(projectionEdge).toBeInTheDocument();
  });

  it('groups upstream physical columns into table containers in column view', () => {
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

    expect(screen.getByText('dwd_order_di', { selector: '.relation-node__title' })).toBeInTheDocument();
    expect(screen.getAllByText('order_no', { selector: '.column-row__label' })).toHaveLength(2);
    expect(screen.getByText('user_id', { selector: '.column-row__label' })).toBeInTheDocument();
    expect(screen.getByText('uid', { selector: '.column-row__label' })).toBeInTheDocument();
    expect(screen.queryByText('dwd_order_di.order_no', { selector: '.title' })).not.toBeInTheDocument();
    expect(screen.queryByText('dwd_order_di.user_id', { selector: '.title' })).not.toBeInTheDocument();
    expect(container.querySelectorAll('path.edge.projection')).toHaveLength(2);
  });

  it('selects a column row without selecting the whole relation', () => {
    const state = baseState({
      graphViewMode: 'column',
      backendGraph: {
        nodes: [
          { id: 'physical_table:dwd_order_di', entityId: 'physical_table:dwd_order_di', type: 'table', label: 'dwd_order_di', x: 0, y: 0 },
          { id: 'physical_column:dwd_order_di.order_no', entityId: 'physical_column:dwd_order_di.order_no', type: 'column', label: 'dwd_order_di.order_no', x: 0, y: 0 },
          { id: 'output_column:order_no', entityId: 'output_column:order_no', type: 'output_field', label: 'order_no', x: 0, y: 0 },
          { id: 'query_result:final', entityId: 'query_result:final', type: 'output', label: 'Query Result', x: 0, y: 0 },
        ],
        edges: [
          { id: 'e1', source: 'physical_column:dwd_order_di.order_no', target: 'output_column:order_no', type: 'projection' },
          { id: 'e2', source: 'output_column:order_no', target: 'query_result:final', type: 'output' },
        ],
      },
    });
    const setState = vi.fn();
    const { container } = render(<LineageCanvas state={state} setState={setState} />);

    const sourceRow = container.querySelector('.column-row[data-role="source"][data-entity-id="physical_column\\:dwd_order_di\\.order_no"]') as HTMLElement;
    fireEvent.click(sourceRow);

    const updater = setState.mock.calls[0][0] as (s: WorkbenchState) => WorkbenchState;
    expect(updater(state).selectedEntity).toBe('physical_column:dwd_order_di.order_no');
  });

  it('highlights only the selected column lineage instead of every field in the same relation', () => {
    const state = baseState({
      graphViewMode: 'column',
      selectedEntity: 'output_column:order_no',
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
          { id: 'e1', source: 'physical_column:dwd_order_di.order_no', target: 'output_column:order_no', type: 'projection' },
          { id: 'e2', source: 'physical_column:dwd_order_di.user_id', target: 'output_column:uid', type: 'projection' },
          { id: 'e3', source: 'output_column:order_no', target: 'query_result:final', type: 'output' },
          { id: 'e4', source: 'output_column:uid', target: 'query_result:final', type: 'output' },
        ],
      },
    });

    const { container } = render(<LineageCanvas state={state} setState={vi.fn()} />);
    const selectedSource = container.querySelector('.column-row[data-entity-id="physical_column\\:dwd_order_di\\.order_no"]') as HTMLElement;
    const siblingSource = container.querySelector('.column-row[data-entity-id="physical_column\\:dwd_order_di\\.user_id"]') as HTMLElement;
    const selectedOutput = container.querySelector('.column-row[data-entity-id="output_column\\:order_no"]') as HTMLElement;
    const siblingOutput = container.querySelector('.column-row[data-entity-id="output_column\\:uid"]') as HTMLElement;
    const selectedEdge = container.querySelector('path.edge.edge-selected') as SVGPathElement;
    const siblingEdge = Array.from(container.querySelectorAll('path.edge.projection')).find((edge) => edge !== selectedEdge) as SVGPathElement;

    expect(selectedSource).not.toHaveClass('dimmed');
    expect(selectedOutput).not.toHaveClass('dimmed');
    expect(siblingSource).toHaveClass('dimmed');
    expect(siblingOutput).toHaveClass('dimmed');
    expect(selectedEdge).toBeInTheDocument();
    expect(siblingEdge).toHaveClass('dimmed');
    expect(container.querySelector('.relation-node[data-column-selected="true"][data-selected="true"]')).not.toBeInTheDocument();
  });

  it('toggles relation collapse without selecting the relation', () => {
    const state = baseState({
      graphViewMode: 'column',
      backendGraph: {
        nodes: [
          { id: 'physical_table:dwd_order_di', entityId: 'physical_table:dwd_order_di', type: 'table', label: 'dwd_order_di', x: 0, y: 0 },
          { id: 'physical_column:dwd_order_di.order_no', entityId: 'physical_column:dwd_order_di.order_no', type: 'column', label: 'dwd_order_di.order_no', x: 0, y: 0 },
          { id: 'output_column:order_no', entityId: 'output_column:order_no', type: 'output_field', label: 'order_no', x: 0, y: 0 },
          { id: 'query_result:final', entityId: 'query_result:final', type: 'output', label: 'Query Result', x: 0, y: 0 },
        ],
        edges: [
          { id: 'e1', source: 'physical_column:dwd_order_di.order_no', target: 'output_column:order_no', type: 'projection' },
          { id: 'e2', source: 'output_column:order_no', target: 'query_result:final', type: 'output' },
        ],
      },
    });
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    fireEvent.click(screen.getAllByLabelText('Collapse relation columns')[0]);

    const updater = setState.mock.calls[0][0] as (s: WorkbenchState) => WorkbenchState;
    const next = updater(state);
    expect(next.collapsedRelationIds['physical_table:dwd_order_di']).toBe(true);
    expect(next.selectedEntity).toBe('out:group');
  });

  it('displays GraphRenderMode stats section', () => {
    const state = baseState();
    const setState = vi.fn();
    render(<LineageCanvas state={state} setState={setState} />);

    const statsTitle = screen.getByText('GraphRenderMode');
    expect(statsTitle).toBeInTheDocument();
  });
});
