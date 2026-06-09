import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DialectConvertPage } from '../DialectConvertPage';

const mockConvertSql = vi.fn();
const mockFormatSql = vi.fn();

vi.mock('../../api/client', () => ({
  convertSql: (...args: unknown[]) => mockConvertSql(...args),
  formatSql: (...args: unknown[]) => mockFormatSql(...args),
}));

vi.mock('@monaco-editor/react', () => ({
  default: ({
    value,
    onChange,
  }: {
    value?: string;
    onChange?: (value: string) => void;
  }) => (
    <div data-testid="monaco-editor">
      <textarea
        data-testid="monaco-textarea"
        value={value ?? ''}
        onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => onChange?.(e.target.value)}
      />
    </div>
  ),
  DiffEditor: ({
    original,
    modified,
    onChange,
  }: {
    original?: string;
    modified?: string;
    onChange?: (value: string) => void;
  }) => (
    <div data-testid="monaco-diff-editor">
      <textarea data-testid="monaco-diff-original" value={original ?? ''} readOnly />
      <textarea
        data-testid="monaco-diff-modified"
        value={modified ?? ''}
        onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => onChange?.(e.target.value)}
      />
    </div>
  ),
  loader: { config: vi.fn() },
}));

describe('DialectConvertPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders convert toolbar and diff toggle', () => {
    render(<DialectConvertPage />);

    expect(screen.getByText('Convert')).toBeInTheDocument();
    expect(screen.getByText('Split Diff')).toBeInTheDocument();
    expect(screen.getByText('Target Only')).toBeInTheDocument();
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

  it('swaps dialect selectors', () => {
    render(<DialectConvertPage />);

    const selects = screen.getAllByRole('combobox');
    expect((selects[0] as HTMLSelectElement).value).toBe('hive');
    expect((selects[1] as HTMLSelectElement).value).toBe('spark');

    fireEvent.click(screen.getByText('Swap'));

    expect((screen.getAllByRole('combobox')[0] as HTMLSelectElement).value).toBe('spark');
    expect((screen.getAllByRole('combobox')[1] as HTMLSelectElement).value).toBe('hive');
  });
});
