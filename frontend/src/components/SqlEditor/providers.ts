import { loader } from '@monaco-editor/react';
import type { editor, languages } from 'monaco-editor';

let loaderConfigured = false;
const registeredMonacoInstances = new WeakSet<object>();
const dialectResolvers = new Map<string, () => string>();

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

export function configureSqlMonacoLoader() {
  if (loaderConfigured) return;
  loader.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.50.0/min/vs' } });
  loaderConfigured = true;
}

export function bindModelDialect(model: editor.ITextModel | null | undefined, getDialect: () => string) {
  if (!model) return;
  dialectResolvers.set(model.uri.toString(), getDialect);
}

export function unbindModelDialect(model: editor.ITextModel | null | undefined) {
  if (!model) return;
  dialectResolvers.delete(model.uri.toString());
}

function resolveDialect(model: editor.ITextModel): string {
  return dialectResolvers.get(model.uri.toString())?.() ?? 'spark';
}

function normalizeDialect(dialect: string): string {
  const value = dialect.trim().toLowerCase();
  if (['spark', 'hive', 'mysql', 'starrocks', 'doris'].includes(value)) return value;
  return 'spark';
}

async function fetchCompletion(
  sql: string,
  line: number,
  col: number,
  dialect: string,
): Promise<CompletionResponse | null> {
  try {
    const response = await fetch('/api/editor/completion', {
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
    if (!response.ok) return null;
    return await response.json();
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
    const response = await fetch('/api/editor/hover', {
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
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export function createCompletionProvider(
  getDialect: (model: editor.ITextModel) => string,
  itemKinds: CompletionItemKindMap,
): languages.CompletionItemProvider {
  return {
    triggerCharacters: ['.', ' '],
    async provideCompletionItems(model, position) {
      const sql = model.getValue();
      if (!sql.trim()) return { suggestions: [] };

      const response = await fetchCompletion(
        sql,
        position.lineNumber,
        position.column,
        getDialect(model),
      );
      if (!response?.candidates?.length) return { suggestions: [] };

      const word = model.getWordUntilPosition(position);
      const suggestions: languages.CompletionItem[] = response.candidates.map((candidate) => ({
        label: candidate.text,
        kind: itemKinds[candidate.type],
        detail: candidate.detail ?? undefined,
        insertText: candidate.text,
        filterText: candidate.text,
        sortText: `${completionPriority(candidate.type)}_${candidate.text.toLowerCase()}`,
        range: {
          startLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endLineNumber: position.lineNumber,
          endColumn: word.endColumn,
        },
      }));

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

export function createHoverProvider(
  getDialect: (model: editor.ITextModel) => string,
): languages.HoverProvider {
  return {
    async provideHover(model, position) {
      const sql = model.getValue();
      if (!sql.trim()) return null;

      const response = await fetchHover(
        sql,
        position.lineNumber,
        position.column,
        getDialect(model),
      );
      if (!response?.hover) return null;

      const hover = response.hover;
      const typeLabel = hover.type === 'table' ? 'Table' : hover.type === 'column' ? 'Column' : 'Identifier';
      const contents = [{ value: `**${typeLabel}**: \`${hover.text ?? ''}\`` }];

      if (hover.data_type) {
        contents.push({ value: `**Type**: ${hover.data_type}` });
      }
      if (hover.comment) {
        contents.push({ value: `**Comment**: ${hover.comment}` });
      }
      if (hover.source) {
        contents.push({ value: `**Source**: \`${hover.source}\`` });
      }

      return {
        contents,
        range: {
          startLineNumber: position.lineNumber,
          startColumn: position.column,
          endLineNumber: position.lineNumber,
          endColumn: position.column,
        },
      };
    },
  };
}

export function registerSqlLanguageProviders(monaco: any) {
  if (registeredMonacoInstances.has(monaco)) return;
  registeredMonacoInstances.add(monaco);
  monaco.languages.registerCompletionItemProvider(
    'sql',
    createCompletionProvider(resolveDialect, {
      keyword: monaco.languages.CompletionItemKind.Keyword,
      function: monaco.languages.CompletionItemKind.Function,
      table: monaco.languages.CompletionItemKind.Class,
      column: monaco.languages.CompletionItemKind.Field,
    }),
  );
  monaco.languages.registerHoverProvider('sql', createHoverProvider(resolveDialect));
}
