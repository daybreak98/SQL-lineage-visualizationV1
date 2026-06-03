import { afterEach, describe, expect, it, vi } from 'vitest';
import type { editor, Position } from 'monaco-editor';
import { createCompletionProvider, type CompletionItemKindMap } from '../providers';

const itemKinds: CompletionItemKindMap = {
  keyword: 17 as any,
  function: 1 as any,
  table: 7 as any,
  column: 4 as any,
};

function createModel(sql: string): editor.ITextModel {
  return {
    getValue: () => sql,
    getWordUntilPosition: () => ({
      word: 'se',
      startColumn: 1,
      endColumn: sql.length + 1,
    }),
  } as unknown as editor.ITextModel;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('createCompletionProvider', () => {
  it('maps backend keyword candidates to Monaco keyword suggestions for se prefix', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        candidates: [
          { text: 'SELECT', type: 'keyword', detail: 'SQL keyword' },
          { text: 'SESSION_USER', type: 'function', detail: 'SQL function' },
        ],
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const provider = createCompletionProvider(() => 'spark', itemKinds);
    const result = await provider.provideCompletionItems(
      createModel('se'),
      { lineNumber: 1, column: 3 } as Position,
      {} as any,
      {} as any,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/editor/completion',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const requestBody = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(requestBody).toMatchObject({
      sql: 'se',
      cursor_line: 1,
      cursor_col: 3,
      dialect: 'spark',
    });

    const suggestions = result?.suggestions ?? [];
    const selectSuggestion = suggestions.find((item) => item.label === 'SELECT');
    expect(selectSuggestion).toMatchObject({
      label: 'SELECT',
      kind: itemKinds.keyword,
      insertText: 'SELECT',
      filterText: 'SELECT',
      detail: 'SQL keyword',
      range: {
        startLineNumber: 1,
        startColumn: 1,
        endLineNumber: 1,
        endColumn: 3,
      },
    });
  });

  it('maps table, column, and function candidates to distinct Monaco kinds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          candidates: [
            { text: 'orders', type: 'table' },
            { text: 'order_id', type: 'column' },
            { text: 'COUNT', type: 'function' },
          ],
        }),
      }),
    );

    const provider = createCompletionProvider(() => 'spark', itemKinds);
    const result = await provider.provideCompletionItems(
      createModel('se'),
      { lineNumber: 1, column: 3 } as Position,
      {} as any,
      {} as any,
    );

    const kindByLabel = new Map(
      (result?.suggestions ?? []).map((item) => [item.label, item.kind]),
    );
    expect(kindByLabel.get('orders')).toBe(itemKinds.table);
    expect(kindByLabel.get('order_id')).toBe(itemKinds.column);
    expect(kindByLabel.get('COUNT')).toBe(itemKinds.function);
  });
});
