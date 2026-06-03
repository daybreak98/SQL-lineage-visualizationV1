import { useEffect, useRef } from 'react';
import Editor, { loader } from '@monaco-editor/react';
import type { editor as monacoEditor } from 'monaco-editor';
import type { SourceLocation, WorkbenchState } from '../types/lineage';
import { createCursorHandler } from './SqlEditor/decorations';
import { createCompletionProvider, createHoverProvider } from './SqlEditor/providers';

loader.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.50.0/min/vs' } });

interface Props {
  sql: string;
  setSql: (value: string) => void;
  state: WorkbenchState;
  dialect: string;
  /** Lookup: entity_id → SourceLocation for bidirectional linking */
  sourceLocations?: Record<string, SourceLocation>;
  /** Called when the Monaco editor is mounted (passes editor instance up) */
  onEditorMounted?: (editor: monacoEditor.IStandaloneCodeEditor) => void;
  /** Called when cursor position matches an entity_id in sourceLocations */
  onCursorEntityChange?: (entityId: string | null) => void;
}

export function SqlEditorPanel({ sql, setSql, state, dialect, sourceLocations, onEditorMounted, onCursorEntityChange }: Props) {
  const editorRef = useRef<monacoEditor.IStandaloneCodeEditor | null>(null);
  const lines = sql.split('\n');

  // Keep refs in sync so the cursor handler always reads latest values
  const sourceLocsRef = useRef(sourceLocations);
  sourceLocsRef.current = sourceLocations;
  const onCursorRef = useRef(onCursorEntityChange);
  onCursorRef.current = onCursorEntityChange;
  const onMountedRef = useRef(onEditorMounted);
  onMountedRef.current = onEditorMounted;

  // Register cursor → source_location listener when editor mounts
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    const disposable = createCursorHandler(sourceLocsRef, onCursorRef)(editor);
    return () => disposable.dispose();
  }, []); // Runs once on mount; refs keep values fresh

  const dialectRef = useRef(dialect);
  dialectRef.current = dialect;
  const providersRegistered = useRef(false);

  const handleMount = (editor: monacoEditor.IStandaloneCodeEditor, monaco: any) => {
    editorRef.current = editor;
    onMountedRef.current?.(editor);

    if (!providersRegistered.current) {
      providersRegistered.current = true;
      monaco.languages.registerCompletionItemProvider(
        'sql',
        createCompletionProvider(() => dialectRef.current, {
          keyword: monaco.languages.CompletionItemKind.Keyword,
          function: monaco.languages.CompletionItemKind.Function,
          table: monaco.languages.CompletionItemKind.Class,
          column: monaco.languages.CompletionItemKind.Field,
        }),
      );
      monaco.languages.registerHoverProvider('sql', createHoverProvider(() => dialectRef.current));
    }
  };

  return (
    <section className="editor">
      <div className="panel-head">
        <div><b>Monaco SqlEditor</b><span className="badge">v1.4</span><span className="badge">{state.trustStatus}</span></div>
        <span>Ctrl/Cmd + Enter</span>
      </div>
      <div className="editor-body" style={{ position: 'relative' }}>
        <Editor
          height="100%"
          language="sql"
          theme="vs"
          value={sql}
          onChange={(value) => setSql(value || '')}
          onMount={handleMount}
          loading={<div style={{ margin: 12, fontSize: 12, color: '#6b7280' }}>Loading Monaco Editor...</div>}
          options={{
            fontSize: 13,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            lineNumbers: 'on',
            lineNumbersMinChars: 4,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            wordWrap: 'on',
            tabSize: 2,
            renderLineHighlight: 'none',
            folding: false,
            glyphMargin: false,
            padding: { top: 12, bottom: 12 },
            automaticLayout: true,
            wordBasedSuggestions: 'off',
            suggest: { showKeywords: true, showSnippets: false },
          }}
        />
      </div>
      <div className="editor-foot">
        <span>Ln {lines.length}, Col 1 · {dialect} · pageMode={state.pageMode}</span>
        <span>Ctrl+Enter to analyze</span>
      </div>
    </section>
  );
}
