import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { editor, IRange } from 'monaco-editor';
import { SqlEditorPanel } from '../components/SqlEditorPanel';
import { applySqlDraftChange, initialWorkbenchState } from '../workbench/state';
import type { Position } from './contract';
import type { createSQLPositionIndex } from './sqlPositionIndex';
import './repository-editor.css';

export default function SubfieldEditor({ sql, setSql, dialect, busy, locate, run, positionIndex }: {
  sql: string; setSql: (sql: string) => void; dialect: string; busy: boolean;
  locate: Position | null; run: () => void;
  positionIndex: ReturnType<typeof createSQLPositionIndex> | null;
}) {
  const [active, setActive] = useState<editor.IStandaloneCodeEditor | null>(null);
  const runRef = useRef(run);
  const lastEvidence = useRef<{ instance: editor.IStandaloneCodeEditor; range: IRange } | null>(null);
  runRef.current = run;
  const state = useMemo(() => applySqlDraftChange(initialWorkbenchState, sql), [sql]);
  const onMount = useCallback((instance: editor.IStandaloneCodeEditor) => setActive(instance), []);
  useEffect(() => {
    if (!active) return;
    active.updateOptions({ readOnly: busy, ariaLabel: 'SQL 原文' });
    const keyboard = active.onKeyDown(event => {
      if ((event.ctrlKey || event.metaKey) && event.browserEvent.key === 'Enter') {
        event.preventDefault();
        if (!busy) runRef.current();
      }
    });
    return () => keyboard.dispose();
  }, [active, busy]);
  useEffect(() => {
    if (!active) return;
    if (!locate) {
      const selection = active.getSelection();
      const last = lastEvidence.current;
      if (last?.instance === active && selection?.equalsRange(last.range)) {
        active.setPosition(selection.getPosition());
      }
      lastEvidence.current = null;
      return;
    }
    if (!positionIndex?.valid(locate)) return;
    const frame = requestAnimationFrame(() => {
      const model = active.getModel();
      if (!model || model.getValue().replace(/\r\n/g, '\n') !== sql.replace(/\r\n/g, '\n')) return;
      const from = positionIndex.editorPosition(locate.start);
      const to = positionIndex.editorPosition(locate.end);
      if (!from || !to) return;
      const range = { startLineNumber: from.lineNumber, startColumn: from.column,
        endLineNumber: to.lineNumber, endColumn: to.column };
      active.setSelection(range);
      lastEvidence.current = { instance: active, range };
      active.revealLineInCenter(from.lineNumber);
      active.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [active, locate, sql, positionIndex]);
  return <SqlEditorPanel sql={sql} setSql={setSql} state={state}
    dialect={dialect === 'hive' ? 'Hive' : 'Spark'} onEditorMounted={onMount} />;
}
