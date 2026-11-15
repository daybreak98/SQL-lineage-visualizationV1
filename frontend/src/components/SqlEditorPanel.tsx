import { useEffect, useRef, useState } from 'react';
import Editor from '@monaco-editor/react';
import type { editor as monacoEditor } from 'monaco-editor';
import type { SourceLocation, WorkbenchState } from '../types/lineage';
import { createCursorHandler } from './SqlEditor/decorations';
import {
  bindModelDialect,
  configureSqlMonacoLoader,
  registerSqlLanguageProviders,
  unbindModelDialect,
} from './SqlEditor/providers';

configureSqlMonacoLoader();

interface Props {
  sql: string;
  setSql: (value: string) => void;
  state: WorkbenchState;
  dialect: string;
  sourceLocations?: Record<string, SourceLocation>;
  onEditorMounted?: (editor: monacoEditor.IStandaloneCodeEditor) => void;
  onCursorEntityChange?: (entityId: string | null) => void;
}

export function SqlEditorPanel({ sql, setSql, state, dialect, sourceLocations, onEditorMounted, onCursorEntityChange }: Props) {
  const [active, setActive] = useState<monacoEditor.IStandaloneCodeEditor | null>(null);
  const [cursor, setCursor] = useState({ lineNumber: 1, column: 1 });
  useEffect(() => {
    if (!active) return;
    const position = active.getPosition();
    if (position) setCursor(position);
    const subscription = active.onDidChangeCursorPosition(({ position: next }) => setCursor(next));
    return () => subscription.dispose();
  }, [active]);
  const sourceLocsRef = useRef(sourceLocations);
  sourceLocsRef.current = sourceLocations;
  const onCursorRef = useRef(onCursorEntityChange);
  onCursorRef.current = onCursorEntityChange;
  const onMountedRef = useRef(onEditorMounted);
  onMountedRef.current = onEditorMounted;
  const dialectRef = useRef(dialect);
  dialectRef.current = dialect;

  const handleMount = (editor: monacoEditor.IStandaloneCodeEditor, monaco: any) => {
    setActive(editor);
    onMountedRef.current?.(editor);
    createCursorHandler(sourceLocsRef, onCursorRef)(editor);
    registerSqlLanguageProviders(monaco);

    const model = editor.getModel();
    bindModelDialect(model, () => dialectRef.current);
    editor.onDidDispose(() => unbindModelDialect(model));
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
        <span>Ln {cursor.lineNumber}, Col {cursor.column} | {dialect} | pageMode={state.pageMode}</span>
        <span>Ctrl+Enter to analyze</span>
      </div>
    </section>
  );
}
