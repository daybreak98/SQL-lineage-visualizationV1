import { useEffect } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  default: ({
    value,
    onChange,
    onMount,
  }: {
    value?: string;
    onChange?: (value: string) => void;
    onMount?: (editor: {
      getModel: () => { uri: { toString: () => string } };
      onDidDispose: (handler: () => void) => { dispose: () => void };
    }, monaco: ReturnType<typeof createMonacoStub>) => void;
  }) => {
    useEffect(() => {
      onMount?.({
        getModel: () => ({ uri: { toString: () => 'inmemory://editor/standalone.sql' } }),
        onDidDispose: () => ({ dispose: vi.fn() }),
      }, createMonacoStub());
    }, [onMount]);

    return (
      <div data-testid="monaco-editor">
        <textarea
          data-testid="monaco-textarea"
          value={value ?? ''}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => onChange?.(e.target.value)}
        />
      </div>
    );
  },
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
      };
      getModifiedEditor: () => {
        getModel: () => { uri: { toString: () => string } };
        getValue: () => string;
        onDidChangeModelContent: (handler: () => void) => { dispose: () => void };
      };
      onDidDispose: (handler: () => void) => { dispose: () => void };
    }, monaco: ReturnType<typeof createMonacoStub>) => void;
  }) => {
    let modifiedValue = modified ?? '';
    let changeHandler: (() => void) | null = null;

    useEffect(() => {
      onMount?.({
        getOriginalEditor: () => ({
          getModel: () => ({ uri: { toString: () => 'inmemory://diff/original.sql' } }),
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
    }, [onMount]);

    return (
      <div data-testid="monaco-diff-editor">
        <textarea data-testid="monaco-diff-original" value={original ?? ''} readOnly />
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

  it('renders convert toolbar and diff toggle', () => {
    render(<DialectConvertPage />);

    expect(screen.getByText('Convert')).toBeInTheDocument();
    expect(screen.getByText('Show Diff')).toBeInTheDocument();
  });

  it('uses two standalone editors by default with diff overlay toggle', () => {
    render(<DialectConvertPage />);

    expect(screen.getAllByTestId('monaco-editor')).toHaveLength(2);
    expect(screen.queryByTestId('monaco-diff-editor')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Show Diff'));
    expect(screen.getByTestId('monaco-diff-editor')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Hide Diff'));
    expect(screen.queryByTestId('monaco-diff-editor')).not.toBeInTheDocument();
  });

  it('calls convert api and renders target sql', async () => {
    mockConvertSql.mockResolvedValueOnce({
      status: 'success',
      source_dialect: 'hive',
      target_dialect: 'spark',
      converted_sql: 'SELECT 1',
      elapsed_ms: 6,
      diagnostics: [],
    });

    render(<DialectConvertPage />);
    fireEvent.click(screen.getByText('Convert'));

    await waitFor(() => {
      expect(mockConvertSql).toHaveBeenCalled();
    });

    expect(screen.getByDisplayValue('SELECT 1')).toBeInTheDocument();
  });

  it('formats source sql from the toolbar before conversion', async () => {
    mockFormatSql.mockResolvedValueOnce({
      status: 'success',
      dialect: 'hive',
      formatted_sql: 'select\n  user_id\nfrom dwd_order_di',
      diagnostics: [],
    });

    render(<DialectConvertPage />);
    fireEvent.click(screen.getByText('Format Source'));

    await waitFor(() => {
      expect(mockFormatSql).toHaveBeenCalledWith(expect.any(String), 'hive');
    });

    expect((screen.getAllByTestId('monaco-textarea')[0] as HTMLTextAreaElement).value).toBe(
      'select\n  user_id\nfrom dwd_order_di',
    );
  });

  it('shows unsupported function line hints in the bottom status bar', async () => {
    mockConvertSql.mockResolvedValueOnce({
      status: 'partial',
      source_dialect: 'starrocks',
      target_dialect: 'hive',
      converted_sql: 'select\n  bitmap_count(to_bitmap(user_id)) as uv\nfrom dwd_order_di',
      elapsed_ms: 7,
      diagnostics: [
        {
          code: 'FUNCTION_CONVERSION_UNCERTAIN',
          level: 'warning',
          message: 'Line 3: function bitmap_count is not guaranteed to convert correctly.',
          location: { line: 3, col: 3 },
          extra: { function: 'bitmap_count', target_dialect: 'hive' },
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
    expect((selects[0] as HTMLSelectElement).value).toBe('hive');
    expect((selects[1] as HTMLSelectElement).value).toBe('spark');

    fireEvent.click(screen.getByText('Swap'));

    expect((screen.getAllByRole('combobox')[0] as HTMLSelectElement).value).toBe('spark');
    expect((screen.getAllByRole('combobox')[1] as HTMLSelectElement).value).toBe('hive');
  });

  it('edits the target sql directly and shows diff overlay', async () => {
    mockConvertSql.mockResolvedValueOnce({
      status: 'success',
      source_dialect: 'hive',
      target_dialect: 'spark',
      converted_sql: 'SELECT 1',
      elapsed_ms: 6,
      diagnostics: [],
    });

    render(<DialectConvertPage />);
    fireEvent.click(screen.getByText('Convert'));

    await waitFor(() => {
      expect(screen.getByDisplayValue('SELECT 1')).toBeInTheDocument();
    });

    fireEvent.change(screen.getAllByTestId('monaco-textarea')[1], { target: { value: 'SELECT 2' } });

    expect(screen.getByDisplayValue('SELECT 2')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Show Diff'));
    expect(screen.getByTestId('monaco-diff-editor')).toBeInTheDocument();
  });

  it('edits the target sql in diff overlay and syncs to standalone editor', async () => {
    mockConvertSql.mockResolvedValueOnce({
      status: 'success',
      source_dialect: 'hive',
      target_dialect: 'spark',
      converted_sql: 'SELECT 1',
      elapsed_ms: 6,
      diagnostics: [],
    });

    render(<DialectConvertPage />);
    fireEvent.click(screen.getByText('Convert'));

    await waitFor(() => {
      expect(screen.getByDisplayValue('SELECT 1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Show Diff'));
    fireEvent.change(screen.getByTestId('monaco-diff-modified'), { target: { value: 'SELECT 2' } });

    await waitFor(() => {
      expect(screen.getAllByDisplayValue('SELECT 2')).toHaveLength(2);
    });

    fireEvent.click(screen.getByText('Hide Diff'));
    expect(screen.getByDisplayValue('SELECT 2')).toBeInTheDocument();
  });

  it('defaults edit target columns to equal width and supports resizing', () => {
    const { container } = render(<DialectConvertPage />);

    const workspace = container.querySelector('.convert-workspace') as HTMLElement;
    expect(workspace.style.getPropertyValue('--convert-split')).toBe('50%');

    const resizeButton = screen.getByLabelText('Resize source and target SQL editors');
    fireEvent.keyDown(resizeButton, { key: 'ArrowRight' });

    expect(workspace.style.getPropertyValue('--convert-split')).toBe('52%');
  });

  it('resizes edit target columns by dragging the splitter', () => {
    const { container } = render(<DialectConvertPage />);

    const workspace = container.querySelector('.convert-workspace') as HTMLElement;
    Object.defineProperty(workspace, 'getBoundingClientRect', {
      value: () => ({ width: 1000, height: 600, top: 0, left: 0, right: 1000, bottom: 600, x: 0, y: 0, toJSON: () => ({}) }),
    });

    const resizeButton = screen.getByLabelText('Resize source and target SQL editors');
    fireEvent.mouseDown(resizeButton, { clientX: 500 });
    fireEvent.mouseMove(window, { clientX: 600 });
    fireEvent.mouseUp(window);

    expect(workspace.style.getPropertyValue('--convert-split')).toBe('60%');
  });

  it('shows Copy Target button as clean after conversion and dirty after editing', async () => {
    mockConvertSql.mockResolvedValueOnce({
      status: 'success',
      source_dialect: 'hive',
      target_dialect: 'spark',
      converted_sql: 'SELECT 1',
      elapsed_ms: 6,
      diagnostics: [],
    });

    render(<DialectConvertPage />);
    const copyButton = screen.getByText('Copy Target');
    expect(copyButton.className).not.toContain('btn-copy-clean');

    fireEvent.click(screen.getByText('Convert'));

    await waitFor(() => {
      expect(screen.getByDisplayValue('SELECT 1')).toBeInTheDocument();
    });

    expect(copyButton.className).toContain('btn-copy-clean');

    fireEvent.change(screen.getAllByTestId('monaco-textarea')[1], { target: { value: 'SELECT 2' } });

    await waitFor(() => {
      expect(copyButton.className).not.toContain('btn-copy-clean');
    });
  });
});
