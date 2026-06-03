/** Monaco Editor: CompletionProvider + HoverProvider（M21）。
 *
 * 调用后端 /api/editor/completion 和 /api/editor/hover 接口。
 * 后端不可用时静默降级，不报错。
 */

import type { languages, editor, Position, CancellationToken } from 'monaco-editor';

// ── Types ────────────────────────────────────────────────

export interface CompletionCandidate {
  text: string;
  type: 'table' | 'column' | 'keyword' | 'function';
  detail?: string | null;
}

export interface CompletionResponse {
  candidates: CompletionCandidate[];
}

export interface CompletionItemKindMap {
  table: languages.CompletionItemKind;
  column: languages.CompletionItemKind;
  keyword: languages.CompletionItemKind;
  function: languages.CompletionItemKind;
}

export interface HoverInfo {
  text?: string | null;
  type?: string | null;
  comment?: string | null;
  data_type?: string | null;
  source?: string | null;
}

export interface HoverResponse {
  hover?: HoverInfo | null;
}

// ── API call helpers ─────────────────────────────────────

function normalizeDialect(dialect: string): string {
  const val = dialect.trim().toLowerCase();
  if (['spark', 'hive', 'mysql', 'starrocks', 'doris'].includes(val)) return val;
  return 'spark';
}

async function fetchCompletion(
  sql: string,
  line: number,
  col: number,
  dialect: string,
): Promise<CompletionResponse | null> {
  try {
    const res = await fetch('/api/editor/completion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sql,
        cursor_line: line,
        cursor_col: col,
        dialect: normalizeDialect(dialect),
        metadata_version: 'latest',
      }),
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function fetchHover(
  sql: string,
  line: number,
  col: number,
  dialect: string,
): Promise<HoverResponse | null> {
  try {
    const res = await fetch('/api/editor/hover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sql,
        cursor_line: line,
        cursor_col: col,
        dialect: normalizeDialect(dialect),
        metadata_version: 'latest',
      }),
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

// ── CompletionProvider ───────────────────────────────────

/** 创建 CompletionProvider，绑定到当前 model / dialect 获取方法。
 *  @param getDialect 获取当前方言
 *  @param monacoRef 指向 Monaco 实例的 ref（用于取 CompletionItemKind 枚举）
 */
export function createCompletionProvider(
  getDialect: () => string,
  itemKinds: CompletionItemKindMap,
): languages.CompletionItemProvider {
  return {
    triggerCharacters: ['.', ' '],
    async provideCompletionItems(model, position, _context, _token) {
      const sql = model.getValue();
      const line = position.lineNumber;
      const col = position.column;
      const dialect = getDialect();

      if (!sql.trim() || sql.trim().length < 1) return { suggestions: [] };

      const resp = await fetchCompletion(sql, line, col, dialect);
      if (!resp?.candidates?.length) return { suggestions: [] };

      const word = model.getWordUntilPosition(position);
      const suggestions: languages.CompletionItem[] = resp.candidates.map((c) => {
        return {
          label: c.text,
          kind: itemKinds[c.type],
          detail: c.detail ?? undefined,
          insertText: c.text,
          filterText: c.text,
          sortText: `${completionPriority(c.type)}_${c.text.toLowerCase()}`,
          range: {
            startLineNumber: line,
            startColumn: word.startColumn,
            endLineNumber: line,
            endColumn: word.endColumn,
          },
        } as languages.CompletionItem;
      });

      return { suggestions };
    },
  };
}

function completionPriority(type: CompletionCandidate['type']): string {
  switch (type) {
    case 'keyword':
      return '0';
    case 'function':
      return '1';
    case 'table':
      return '2';
    case 'column':
      return '3';
    default:
      return '9';
  }
}

// ── HoverProvider ────────────────────────────────────────

/** 创建 HoverProvider，绑定到当前 model / dialect 获取方法。 */
export function createHoverProvider(
  getDialect: () => string,
): languages.HoverProvider {
  return {
    async provideHover(model, position, _token) {
      const sql = model.getValue();
      const line = position.lineNumber;
      const col = position.column;
      const dialect = getDialect();

      if (!sql.trim()) return null;

      const resp = await fetchHover(sql, line, col, dialect);
      if (!resp?.hover) return null;

      const h = resp.hover as HoverInfo;
      const parts: { value: string }[] = [];

      // 类型标签
      const typeLabel = h.type === 'table' ? '📦 Table' : h.type === 'column' ? '📋 Column' : 'Identifier';
      const header = `**${typeLabel}**: \`${h.text ?? ''}\``;
      parts.push({ value: header });

      if (h.data_type) {
        parts.push({ value: `**Type**: ${h.data_type}` });
      }
      if (h.comment) {
        parts.push({ value: `**Comment**: ${h.comment}` });
      }
      if (h.source) {
        parts.push({ value: `**Source**: \`${h.source}\`` });
      }

      return {
        contents: parts,
        range: {
          startLineNumber: line,
          startColumn: col,
          endLineNumber: line,
          endColumn: col,
        },
      };
    },
  };
}
