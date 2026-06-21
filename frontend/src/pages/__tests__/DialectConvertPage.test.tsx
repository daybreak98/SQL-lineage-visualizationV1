import { useEffect } from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DialectConvertPage } from '../DialectConvertPage';

const mockConvertSql = vi.fn();
const mockFormatSql = vi.fn();

vi.mock('../../api/client', () => ({
  convertSql: (...args: unknown[]) => mockConvertSql(...args),
  formatSql: (...args: unknown[]) => mockFormatSql(...args),
}));

function createMonacoStub() {
  return {
    languages: {
      registerCompletionItemProvider: vi.fn(),
      registerHoverProvider: vi.fn(),
      CompletionItemKind: { Keyword: 17, Function: 1, Class: 7, Field: 4 },
    },
  };
}

vi.mock('@monaco-editor/react', () => ({
  DiffEditor: ({
    original,
    modified,
    onMount,
  }: {
    original?: string;
    modified?: string;
    onMount?: (editor: {
      getOriginalEditor: () => {
        getModel: () => { uri: { toString: () => string } };
        getValue: () => string;
        onDidChangeModelContent: (handler: () => void) => { dispose: () => void };
      };
      getModifiedEditor: () => {
        getModel: () => { uri: { toString: () => string } };
        getValue: () => string;
        onDidChangeModelContent: (handler: () => void) => { dispose: () => void };
      };
      onDidDispose: (handler: () => void) => { dispose: () => void };
    }, monaco: ReturnType<typeof createMonacoStub>) => void;
  }) => {
    let originalValue = (original ?? '').replace(/\r\n/g, '\n');
    let modifiedValue = (modified ?? '').replace(/\r\n/g, '\n');
    let originalChangeHandler: (() => void) | null = null;
    let changeHandler: (() => void) | null = null;

    useEffect(() => {
      onMount?.({
        getOriginalEditor: () => ({
          getModel: () => ({ uri: { toString: () => 'inmemory://diff/original.sql' } }),
          getValue: () => originalValue,
          onDidChangeModelContent: (handler: () => void) => {
            originalChangeHandler = handler;
            return { dispose: vi.fn() };
          },
        }),
        getModifiedEditor: () => ({
          getModel: () => ({ uri: { toString: () => 'inmemory://diff/modified.sql' } }),
          getValue: () => modifiedValue,
          onDidChangeModelContent: (handler: () => void) => {
            changeHandler = handler;
            return { dispose: vi.fn() };
          },
        }),
        onDidDispose: () => ({ dispose: vi.fn() }),
      }, createMonacoStub());
      originalChangeHandler?.();
      changeHandler?.();
    }, [onMount]);

    return (
      <div data-testid="monaco-diff-editor">
        <textarea
          data-testid="monaco-diff-original"
          value={original ?? ''}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
            originalValue = e.target.value;
            originalChangeHandler?.();
          }}
        />
        <textarea
          data-testid="monaco-diff-modified"
          value={modified ?? ''}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
            modifiedValue = e.target.value;
            changeHandler?.();
          }}
        />
      </div>
    );
  },
  loader: { config: vi.fn() },
}));

describe('DialectConvertPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a single editable diff workspace without a view toggle', () => {
    render(<DialectConvertPage />);

    expect(screen.getByText('Convert')).toBeInTheDocument();
    expect(screen.getByTestId('monaco-diff-editor')).toBeInTheDocument();
    expect(screen.queryByText('Show Diff')).not.toBeInTheDocument();
    expect(screen.queryByText('Hide Diff')).not.toBeInTheDocument();
  });

  it('defaults to Spark source and StarRocks target', () => {
    render(<DialectConvertPage />);

    const selects = screen.getAllByRole('combobox');
    expect((selects[0] as HTMLSelectElement).value).toBe('spark');
    expect((selects[1] as HTMLSelectElement).value).toBe('starrocks');
    expect((screen.getByTestId('monaco-diff-original') as HTMLTextAreaElement).value)
      .toContain('with base as');
  });

  it('compresses the empty status area into a single line', () => {
    const { container } = render(<DialectConvertPage />);

    expect(screen.getByText(/Ready to convert SQL between Hive, Spark, and StarRocks\./)).toBeInTheDocument();
    expect(screen.getByText(/No diagnostics\. Convert the SQL to inspect compatibility notes and errors\./)).toBeInTheDocument();
    expect(screen.getByText('No run yet')).toBeInTheDocument();
    expect(container.querySelector('.convert-status-panel.compact')).not.toBeNull();
    expect(container.querySelector('.convert-diagnostics')).toBeNull();
  });

  it('calls convert api and renders target sql', async () => {
    mockConvertSql.mockResolvedValueOnce({
      status: 'success',
      source_dialect: 'spark',
      target_dialect: 'starrocks',
      converted_sql: 'SELECT 1',
      elapsed_ms: 6,
      diagnostics: [],
    });

    render(<DialectConvertPage />);
    fireEvent.click(screen.getByText('Convert'));

    await waitFor(() => {
      expect(mockConvertSql).toHaveBeenCalled();
    });

    expect(screen.getByTestId('monaco-diff-modified')).toHaveValue('SELECT 1');
  });

  it('formats source sql from the source editor header before conversion', async () => {
    mockFormatSql.mockResolvedValueOnce({
      status: 'success',
      dialect: 'spark',
      formatted_sql: 'select\n  user_id\nfrom dwd_order_di',
      diagnostics: [],
    });

    render(<DialectConvertPage />);
    const sourceHeader = screen.getByText('Source SQL').closest('.convert-diff-head-side') as HTMLElement;
    fireEvent.click(within(sourceHeader).getByText('Format'));

    await waitFor(() => {
      expect(mockFormatSql).toHaveBeenCalledWith(expect.any(String), 'spark');
    });

    expect(screen.getByTestId('monaco-diff-original')).toHaveValue(
      'select\n  user_id\nfrom dwd_order_di',
    );
  });

  it('shows unsupported function line hints in the bottom status bar', async () => {
    mockConvertSql.mockResolvedValueOnce({
      status: 'partial',
      source_dialect: 'spark',
      target_dialect: 'starrocks',
      converted_sql: 'select\n  bitmap_count(to_bitmap(user_id)) as uv\nfrom dwd_order_di',
      elapsed_ms: 7,
      diagnostics: [
        {
          code: 'FUNCTION_CONVERSION_UNCERTAIN',
          level: 'warning',
          message: 'Line 3: function bitmap_count is not guaranteed to convert correctly.',
          location: { line: 3, col: 3 },
          extra: { function: 'bitmap_count', target_dialect: 'starrocks' },
        },
      ],
    });

    render(<DialectConvertPage />);
    fireEvent.click(screen.getByText('Convert'));

    await waitFor(() => {
      expect(screen.getByText(/Line 3: bitmap_count/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Unsupported or uncertain function conversion/)).toBeInTheDocument();
  });

  it('swaps dialect selectors', () => {
    render(<DialectConvertPage />);

    const selects = screen.getAllByRole('combobox');
    expect((selects[0] as HTMLSelectElement).value).toBe('spark');
    expect((selects[1] as HTMLSelectElement).value).toBe('starrocks');

    fireEvent.click(screen.getByText('Swap'));

    expect((screen.getAllByRole('combobox')[0] as HTMLSelectElement).value).toBe('starrocks');
    expect((screen.getAllByRole('combobox')[1] as HTMLSelectElement).value).toBe('spark');
  });

  it('uses source edits from the unified diff editor for conversion', async () => {
    mockConvertSql.mockResolvedValue({
      status: 'success',
      source_dialect: 'spark',
      target_dialect: 'starrocks',
      converted_sql: 'SELECT 1',
      elapsed_ms: 6,
      diagnostics: [],
    });

    render(<DialectConvertPage />);
    fireEvent.change(screen.getByTestId('monaco-diff-original'), { target: { value: 'SELECT 42' } });
    fireEvent.click(screen.getByText('Convert'));

    await waitFor(() => {
      expect(mockConvertSql).toHaveBeenCalledWith('SELECT 42', 'spark', 'starrocks');
    });
  });

  it('edits the target sql directly in the unified diff editor', async () => {
    mockConvertSql.mockResolvedValueOnce({
      status: 'success',
      source_dialect: 'spark',
      target_dialect: 'starrocks',
      converted_sql: 'SELECT 1',
      elapsed_ms: 6,
      diagnostics: [],
    });

    render(<DialectConvertPage />);
    fireEvent.click(screen.getByText('Convert'));

    await waitFor(() => {
      expect(screen.getByTestId('monaco-diff-modified')).toHaveValue('SELECT 1');
    });

    fireEvent.change(screen.getByTestId('monaco-diff-modified'), { target: { value: 'SELECT 2' } });

    await waitFor(() => {
      expect(screen.getByTestId('monaco-diff-modified')).toHaveValue('SELECT 2');
    });
  });

  it('shows Copy Target as ready after conversion and stale after either editor changes', async () => {
    mockConvertSql.mockResolvedValue({
      status: 'success',
      source_dialect: 'spark',
      target_dialect: 'starrocks',
      converted_sql: 'SELECT 1\r\nFROM target_table',
      elapsed_ms: 6,
      diagnostics: [],
    });

    render(<DialectConvertPage />);
    const copyButton = screen.getByText('Copy Target');
    expect(copyButton.className).not.toContain('btn-copy-ready');

    fireEvent.click(screen.getByText('Convert'));

    await waitFor(() => {
      expect(screen.getByTestId('monaco-diff-modified')).toHaveValue('SELECT 1\nFROM target_table');
    });

    expect(copyButton.className).toContain('btn-copy-ready');

    fireEvent.change(screen.getByTestId('monaco-diff-original'), { target: { value: 'SELECT 2' } });

    await waitFor(() => {
      expect(copyButton.className).not.toContain('btn-copy-ready');
    });

    fireEvent.click(screen.getByText('Convert'));
    await waitFor(() => expect(copyButton.className).toContain('btn-copy-ready'));

    fireEvent.change(screen.getByTestId('monaco-diff-modified'), { target: { value: 'SELECT 3' } });
    await waitFor(() => expect(copyButton.className).not.toContain('btn-copy-ready'));
  });
});
