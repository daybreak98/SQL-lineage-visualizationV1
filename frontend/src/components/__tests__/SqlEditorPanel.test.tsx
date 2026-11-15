import { describe, it, expect, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { SqlEditorPanel } from '../SqlEditorPanel';

const mock = vi.hoisted(() => ({ mount: undefined as ((active: any, monaco: any) => void) | undefined }));
vi.mock('../SqlEditor/providers', () => ({
  bindModelDialect: vi.fn(), configureSqlMonacoLoader: vi.fn(),
  registerSqlLanguageProviders: vi.fn(), unbindModelDialect: vi.fn(),
}));
vi.mock('../SqlEditor/decorations', () => ({ createCursorHandler: () => vi.fn() }));

// Mock Monaco Editor — avoid loading the full editor in jsdom
vi.mock('@monaco-editor/react', () => ({
  default: ({
    value,
    onChange,
    loading,
    onMount,
  }: {
    value?: string;
    onChange?: (v: string) => void;
    loading?: React.ReactNode;
    onMount?: typeof mock.mount;
  }) => {
    mock.mount = onMount;
    return <div data-testid="monaco-editor">
      <textarea
        data-testid="monaco-textarea"
        value={value ?? ''}
        onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
          onChange?.(e.target.value)
        }
        readOnly
      />
      {loading}
    </div>;
  },
  DiffEditor: ({
    original,
    modified,
  }: {
    original?: string;
    modified?: string;
  }) => (
    <div data-testid="monaco-diff-editor">
      <textarea data-testid="monaco-diff-original" value={original ?? ''} readOnly />
      <textarea data-testid="monaco-diff-modified" value={modified ?? ''} readOnly />
    </div>
  ),
  loader: {
    config: vi.fn(),
  },
}));

// ── helper: build a minimal WorkbenchState shape ─────────────
function state(overrides: Record<string, unknown> = {}) {
  return {
    pageMode: 'analyzed',
    analysisStatus: 'success',
    trustStatus: 'trusted',
    selectedEntity: 'out:group',
    ...overrides,
  } as any;
}

describe('SqlEditorPanel', () => {
  const baseProps = {
    sql: 'SELECT * FROM users',
    setSql: vi.fn(),
    dialect: 'spark',
    state: state(),
  };

  // ── Render basics ──────────────────────────────────────────

  it('renders Monaco editor with SQL content', () => {
    render(<SqlEditorPanel {...baseProps} />);
    const textarea = screen.getByTestId('monaco-textarea');
    expect(textarea).toBeInTheDocument();
    expect(textarea).toHaveValue('SELECT * FROM users');
  });

  it('renders the panel head with Monaco SqlEditor label', () => {
    render(<SqlEditorPanel {...baseProps} />);
    expect(screen.getByText(/Monaco SqlEditor/)).toBeInTheDocument();
  });

  // ── Footer info ────────────────────────────────────────────

  it('shows dialect in footer', () => {
    render(<SqlEditorPanel {...baseProps} dialect="hive" />);
    // footer contains "· hive ·"
    const foot = document.querySelector('.editor-foot');
    expect(foot?.textContent).toMatch(/hive/);
  });

  it('shows the live cursor position instead of the total SQL line count', () => {
    const multiLineSql = 'SELECT 1\nSELECT 2\nSELECT 3';
    render(<SqlEditorPanel {...baseProps} sql={multiLineSql} />);
    const dispose = vi.fn();
    let notify: ((event: { position: { lineNumber: number; column: number } }) => void) | undefined;
    const active = {
      getPosition: () => ({ lineNumber: 1, column: 1 }),
      onDidChangeCursorPosition: (fn: typeof notify) => { notify = fn; return { dispose }; },
      getModel: () => null,
      onDidDispose: vi.fn(),
    };
    act(() => mock.mount?.(active, {}));
    expect(screen.getByText(/Ln 1, Col 1/)).toBeInTheDocument();
    act(() => notify?.({ position: { lineNumber: 2, column: 5 } }));
    expect(screen.getByText(/Ln 2, Col 5/)).toBeInTheDocument();
  });

  it('shows pageMode in footer', () => {
    render(<SqlEditorPanel {...baseProps} />);
    expect(screen.getByText(/pageMode=analyzed/)).toBeInTheDocument();
  });

  // ── Trust badges ───────────────────────────────────────────

  it('shows trusted badge when trustStatus is trusted', () => {
    render(<SqlEditorPanel {...baseProps} />);
    const badges = screen.getAllByText('trusted');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it('shows untrusted badge when trustStatus is untrusted', () => {
    render(
      <SqlEditorPanel
        {...baseProps}
        state={state({ trustStatus: 'untrusted', pageMode: 'ready' })}
      />,
    );
    const badges = screen.getAllByText('untrusted');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it('shows stale badge when trustStatus is stale', () => {
    render(
      <SqlEditorPanel
        {...baseProps}
        state={state({ trustStatus: 'stale', pageMode: 'dirty' })}
      />,
    );
    const badges = screen.getAllByText('stale');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  // ── Source location highlight ──────────────────────────────

  it('displays keyboard shortcut hint in footer', () => {
    render(<SqlEditorPanel {...baseProps} />);
    expect(
      screen.getByText(/Ctrl\+Enter/i),
    ).toBeInTheDocument();
  });
});
