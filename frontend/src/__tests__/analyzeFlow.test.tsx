import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import App from '../App';

// ══════════════════════════════════════════════════════════════
//  Mocks
// ══════════════════════════════════════════════════════════════

// Monaco Editor — avoid loading the full editor in jsdom
vi.mock('@monaco-editor/react', () => ({
  default: ({
    value,
    onChange,
  }: {
    value?: string;
    onChange?: (v: string) => void;
  }) => (
    <div data-testid="monaco-editor">
      <textarea
        data-testid="monaco-textarea"
        value={value ?? ''}
        onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
          onChange?.(e.target.value)
        }
        readOnly
      />
    </div>
  ),
  loader: { config: vi.fn() },
}));

// API client — control responses from test
const mockAnalyzeSql = vi.fn();
const mockFormatSql = vi.fn();
const mockGetHealth = vi.fn();
const mockListMetadataTables = vi.fn();
const mockListMetadataColumns = vi.fn();

vi.mock('../api/client', () => ({
  analyzeSql: (...args: unknown[]) => mockAnalyzeSql(...args),
  formatSql: (...args: unknown[]) => mockFormatSql(...args),
  getHealth: (...args: unknown[]) => mockGetHealth(...args),
  listMetadataTables: (...args: unknown[]) => mockListMetadataTables(...args),
  listMetadataColumns: (...args: unknown[]) => mockListMetadataColumns(...args),
  previewMetadata: vi.fn(),
  commitMetadata: vi.fn(),
}));

// ══════════════════════════════════════════════════════════════
//  Helpers
// ══════════════════════════════════════════════════════════════

const successResult = {
  analysis_id: 'test-analysis-1',
  status: 'success' as const,
  tables_extracted: ['users', 'orders'],
  columns_extracted: ['id', 'name', 'amount'],
  diagnostics_report: { diagnostics: [] },
};

const columnGraphResult = {
  analysis_id: 'analysis:c05',
  status: 'success' as const,
  graph_view_model: {
    view_mode: 'table',
    nodes: [
      { id: 'physical_table:t', node_type: 'table', label: 't' },
      { id: 'query_result:final', node_type: 'output', label: 'Query Result' },
      { id: 'physical_column:t.a', node_type: 'physical_column', label: 't.a' },
      { id: 'output_column:a', node_type: 'output_column', label: 'a' },
    ],
    edges: [
      {
        id: 'edge:physical_table:t->query_result:final',
        source: 'physical_table:t',
        target: 'query_result:final',
        edge_type: 'table_to_result',
      },
      {
        id: 'edge:physical_column:t.a->output_column:a',
        source: 'physical_column:t.a',
        target: 'output_column:a',
        edge_type: 'column_lineage',
      },
    ],
  },
  output_fields: [{ name: 'a', display_name: 'a', expression: 'a', source_type: 'unknown' }],
  diagnostics_report: { diagnostics: [] },
  summary: { node_count: 4, edge_count: 2, output_field_count: 1 },
};

const c04JoinColumnGraphResult = {
  analysis_id: 'analysis:c05',
  status: 'success' as const,
  graph_view_model: {
    view_mode: 'table',
    nodes: [
      { id: 'physical_table:dim_user_df', node_type: 'table', label: 'dim_user_df' },
      { id: 'physical_table:dwd_order_di', node_type: 'table', label: 'dwd_order_di' },
      { id: 'query_result:final', node_type: 'output', label: 'Query Result' },
      { id: 'physical_column:dim_user_df.country_name', node_type: 'physical_column', label: 'dim_user_df.country_name' },
      { id: 'output_column:country_name', node_type: 'output_column', label: 'country_name' },
      { id: 'physical_column:dwd_order_di.order_no', node_type: 'physical_column', label: 'dwd_order_di.order_no' },
      { id: 'output_column:order_no', node_type: 'output_column', label: 'order_no' },
    ],
    edges: [
      {
        id: 'edge:physical_table:dim_user_df->query_result:final',
        source: 'physical_table:dim_user_df',
        target: 'query_result:final',
        edge_type: 'table_to_result',
      },
      {
        id: 'edge:physical_table:dwd_order_di->query_result:final',
        source: 'physical_table:dwd_order_di',
        target: 'query_result:final',
        edge_type: 'table_to_result',
      },
      {
        id: 'edge:physical_column:dim_user_df.country_name->output_column:country_name',
        source: 'physical_column:dim_user_df.country_name',
        target: 'output_column:country_name',
        edge_type: 'column_lineage',
      },
      {
        id: 'edge:physical_column:dwd_order_di.order_no->output_column:order_no',
        source: 'physical_column:dwd_order_di.order_no',
        target: 'output_column:order_no',
        edge_type: 'column_lineage',
      },
    ],
  },
  output_fields: [
    { name: 'country_name', display_name: 'country_name', expression: 'u.country_name', source_type: 'unknown' },
    { name: 'order_no', display_name: 'order_no', expression: 'o.order_no', source_type: 'unknown' },
  ],
  diagnostics_report: { diagnostics: [] },
  summary: { node_count: 7, edge_count: 4, output_field_count: 2 },
};

const c05CteStructureResult = {
  analysis_id: 'analysis:c05',
  status: 'success' as const,
  graph_view_model: {
    view_mode: 'subquery_dependency',
    nodes: [
      { id: 'physical_table:dwd_order_di', node_type: 'table', label: 'dwd_order_di' },
      { id: 'cte:order_base', node_type: 'cte', label: 'order_base' },
      { id: 'cte:metric_base', node_type: 'cte', label: 'metric_base' },
      { id: 'query_result:final', node_type: 'output', label: 'Query Result' },
    ],
    edges: [
      {
        id: 'edge:physical_table:dwd_order_di->cte:order_base',
        source: 'physical_table:dwd_order_di',
        target: 'cte:order_base',
        edge_type: 'table_to_cte',
      },
      {
        id: 'edge:cte:order_base->cte:metric_base',
        source: 'cte:order_base',
        target: 'cte:metric_base',
        edge_type: 'cte_dependency',
      },
      {
        id: 'edge:cte:metric_base->query_result:final',
        source: 'cte:metric_base',
        target: 'query_result:final',
        edge_type: 'cte_to_result',
      },
    ],
  },
  output_fields: [
    { name: 'user_id', display_name: 'user_id', expression: 'user_id', source_type: 'unknown' },
    { name: 'order_cnt', display_name: 'order_cnt', expression: 'order_cnt', source_type: 'unknown' },
    { name: 'gmv', display_name: 'gmv', expression: 'gmv', source_type: 'unknown' },
  ],
  diagnostics_report: { diagnostics: [] },
  summary: { node_count: 4, edge_count: 3, output_field_count: 3 },
};

const failedResult = {
  analysis_id: 'test-failed-1',
  status: 'failed' as const,
  tables_extracted: [],
  columns_extracted: [],
  diagnostics_report: {
    diagnostics: [
      {
        code: 'PARSE_ERROR',
        level: 'error' as const,
        message: 'Syntax error',
        details: {},
      },
    ],
  },
};

const partialResult = {
  analysis_id: 'test-partial-1',
  status: 'partial' as const,
  tables_extracted: ['users'],
  columns_extracted: ['id'],
  diagnostics_report: {
    diagnostics: [
      {
        code: 'WARNING',
        level: 'warning' as const,
        message: 'Incomplete metadata',
        details: {},
      },
    ],
  },
};

// ══════════════════════════════════════════════════════════════
//  Tests
// ══════════════════════════════════════════════════════════════

describe('Analyze Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: backend is healthy with metadata present
    mockGetHealth.mockResolvedValue({
      status: 'ok',
      service: 'sql-lineage',
      version: '1.0.0',
    });
    mockListMetadataTables.mockResolvedValue({
      tables: [{ name: 'users' }, { name: 'orders' }],
      total: 2,
    });
  });

  // ── Initial render ─────────────────────────────────────────

  it('renders the app shell without crashing', () => {
    render(<App />);
    expect(screen.getByText('SQL Lineage')).toBeInTheDocument();
  });

  it('shows Analyze button on load', () => {
    render(<App />);
    const analyzeBtn = screen.getByText('Analyze');
    expect(analyzeBtn).toBeInTheDocument();
    expect(analyzeBtn.tagName).toBe('BUTTON');
  });

  it('does not show a default lineage graph before analysis', () => {
    render(<App />);

    expect(screen.queryByText('dwd_order_di', { selector: '.title' })).not.toBeInTheDocument();
    expect(screen.queryByText('Query Result', { selector: '.title' })).not.toBeInTheDocument();
  });

  // ── Loading / analyzing state ──────────────────────────────

  it('shows loading state (Cancel button) during analyze', async () => {
    // Make analyzeSql never resolve so we stay in "analyzing"
    mockAnalyzeSql.mockReturnValue(new Promise(() => {}));

    render(<App />);

    fireEvent.click(screen.getByText('Analyze'));

    await waitFor(() => {
      expect(screen.getByText('Cancel')).toBeInTheDocument();
    });

    // The state pill should show 'analyzing'
    await waitFor(() => {
      const pills = screen.getAllByText(/analyzing/);
      expect(pills.length).toBeGreaterThan(0);
    });
  });

  // ── Analyze success ────────────────────────────────────────

  it('shows trusted state after analyze success', async () => {
    mockAnalyzeSql.mockResolvedValueOnce(successResult);

    render(<App />);

    fireEvent.click(screen.getByText('Analyze'));

    await waitFor(() => {
      const trustedEls = screen.getAllByText('trusted');
      expect(trustedEls.length).toBeGreaterThan(0);
    });
  });

  it('shows analyzed status after analyze success', async () => {
    mockAnalyzeSql.mockResolvedValueOnce(successResult);

    render(<App />);

    fireEvent.click(screen.getByText('Analyze'));

    await waitFor(() => {
      const els = screen.getAllByText(/analyzed/);
      // "analyzed" appears in TopBar status pill
      expect(els.length).toBeGreaterThan(0);
    });
  });

  it('renders backend table structure by default and keeps column graph available', async () => {
    mockAnalyzeSql.mockResolvedValueOnce(columnGraphResult);

    render(<App />);

    fireEvent.click(screen.getByText('Analyze'));

    await waitFor(() => {
      expect(screen.getByText('t', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('Query Result', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('view: table')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Column'));

    await waitFor(() => {
      expect(screen.getByText('t.a', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('view: column')).toBeInTheDocument();
    });
  });

  it('renders C04 join alias table structure by default and column graph on demand', async () => {
    mockAnalyzeSql.mockResolvedValueOnce(c04JoinColumnGraphResult);

    render(<App />);

    fireEvent.click(screen.getByText('Analyze'));

    await waitFor(() => {
      expect(screen.getByText('dim_user_df', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('dwd_order_di', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('Query Result', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('view: table')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Column'));

    await waitFor(() => {
      expect(screen.getByText('dim_user_df.country_name', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('dwd_order_di.order_no', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('view: column')).toBeInTheDocument();
    });
  });

  it('renders C05 CTE structure graph as the default subquery dependency view', async () => {
    mockAnalyzeSql.mockResolvedValueOnce(c05CteStructureResult);

    render(<App />);

    fireEvent.click(screen.getByText('Analyze'));

    await waitFor(() => {
      expect(screen.getByText('dwd_order_di', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('order_base', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('metric_base', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('Query Result', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('view: subquery')).toBeInTheDocument();
    });

    const metricNode = screen.getByText('metric_base', { selector: '.title' }).closest('.node') as HTMLElement;
    const resultNode = screen.getByText('Query Result', { selector: '.title' }).closest('.node') as HTMLElement;
    expect(parseFloat(resultNode.style.left)).toBeGreaterThan(parseFloat(metricNode.style.left));

    fireEvent.click(screen.getByText('Table'));

    await waitFor(() => {
      expect(screen.queryByText('order_base', { selector: '.title' })).not.toBeInTheDocument();
      expect(screen.queryByText('metric_base', { selector: '.title' })).not.toBeInTheDocument();
      expect(screen.getByText('dwd_order_di', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('Query Result', { selector: '.title' })).toBeInTheDocument();
      expect(screen.getByText('view: table')).toBeInTheDocument();
    });

    const tableNode = screen.getByText('dwd_order_di', { selector: '.title' }).closest('.node') as HTMLElement;
    const tableResultNode = screen.getByText('Query Result', { selector: '.title' }).closest('.node') as HTMLElement;
    expect(parseFloat(tableResultNode.style.left) - parseFloat(tableNode.style.left)).toBeLessThan(320);

    fireEvent.click(screen.getByText('Column'));

    await waitFor(() => {
      expect(screen.queryByText('order_base', { selector: '.title' })).not.toBeInTheDocument();
      expect(screen.queryByText('metric_base', { selector: '.title' })).not.toBeInTheDocument();
      expect(screen.queryByText('dwd_order_di', { selector: '.title' })).not.toBeInTheDocument();
      expect(screen.queryByText('Query Result', { selector: '.title' })).not.toBeInTheDocument();
      expect(screen.getByText('view: column')).toBeInTheDocument();
    });
  });

  // ── Analyze failure ────────────────────────────────────────

  it('shows error state on analyze failure (backend returns failed)', async () => {
    mockAnalyzeSql.mockResolvedValueOnce(failedResult);

    render(<App />);

    fireEvent.click(screen.getByText('Analyze'));

    await waitFor(() => {
      const failedEls = screen.getAllByText(/failed/);
      expect(failedEls.length).toBeGreaterThan(0);
    });
  });

  it('shows error state on network error', async () => {
    mockAnalyzeSql.mockRejectedValueOnce(new Error('Network failure'));

    render(<App />);

    fireEvent.click(screen.getByText('Analyze'));

    await waitFor(() => {
      const failedEls = screen.getAllByText(/failed/);
      expect(failedEls.length).toBeGreaterThan(0);
    });
  });

  // ── Dirty / stale after edit ───────────────────────────────

  it('marks state as dirty/stale when SQL is changed after analyze', async () => {
    mockAnalyzeSql.mockResolvedValueOnce(successResult);

    render(<App />);

    // 1. Run analyze — get to trusted state
    fireEvent.click(screen.getByText('Analyze'));

    await waitFor(() => {
      const trustedEls = screen.getAllByText('trusted');
      expect(trustedEls.length).toBeGreaterThan(0);
    });

    // 2. Edit the SQL via mocked Monaco textarea
    const textarea = screen.getByTestId('monaco-textarea');
    fireEvent.change(textarea, {
      target: { value: 'SELECT * FROM new_table' },
    });

    // 3. Should show stale / dirty
    await waitFor(() => {
      const staleEls = screen.getAllByText('stale');
      expect(staleEls.length).toBeGreaterThan(0);
    });

    // 4. Button should now say "Re-analyze" (pageMode === 'dirty')
    expect(screen.getByText('Re-analyze')).toBeInTheDocument();
  });

  // ── Partial analysis ───────────────────────────────────────

  it('shows trusted state for partial analysis', async () => {
    mockAnalyzeSql.mockResolvedValueOnce(partialResult);

    render(<App />);

    fireEvent.click(screen.getByText('Analyze'));

    await waitFor(() => {
      const trustedEls = screen.getAllByText('trusted');
      expect(trustedEls.length).toBeGreaterThan(0);
    });
  });

  // ── Load Example button ────────────────────────────────────

  it('keeps drawer collapsed after partial analysis until the user opens it', async () => {
    mockAnalyzeSql.mockResolvedValueOnce(partialResult);

    render(<App />);

    fireEvent.click(screen.getByText('Analyze'));

    await waitFor(() => {
      const partialEls = screen.getAllByText(/partial/);
      expect(partialEls.length).toBeGreaterThan(0);
    });

    expect(document.querySelector('.drawer.open')).toBeNull();
  });

  it('resets state when Load Example is clicked after analyze', async () => {
    mockAnalyzeSql.mockResolvedValueOnce(successResult);

    render(<App />);

    // Run analyze first
    fireEvent.click(screen.getByText('Analyze'));

    await waitFor(() => {
      const trustedEls = screen.getAllByText('trusted');
      expect(trustedEls.length).toBeGreaterThan(0);
    });

    // Click Load Example
    fireEvent.click(screen.getByText('Load Example'));

    await waitFor(() => {
      const untrustedEls = screen.getAllByText('untrusted');
      expect(untrustedEls.length).toBeGreaterThan(0);
    });
  });
});
