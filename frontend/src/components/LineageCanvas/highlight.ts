import type { SourceLocation } from '../../types/lineage';
import type { editor as monacoEditor, IRange } from 'monaco-editor';

// ── Canvas node → Monaco editor navigation ──────────────

/**
 * Reveal and select the SQL range corresponding to the given entityId
 * in the Monaco editor. The range is derived from the entity's
 * SourceLocation entry.
 *
 * If no SourceLocation exists for the entityId, calls the optional
 * onNoLocation callback for graceful degradation (e.g., a brief
 * non-error status message).
 *
 * Monaco line/column numbers are 1-based — the SourceLocation
 * values are expected to already be 1-based.
 */
export function revealInEditor(
  editor: monacoEditor.IStandaloneCodeEditor | null,
  entityId: string,
  sourceLocations: Record<string, SourceLocation> | undefined | null,
  onNoLocation?: (entityId: string) => void,
): void {
  if (!editor) return;

  const loc = sourceLocations?.[entityId];

  if (!loc) {
    // Graceful degradation — not a hard error
    onNoLocation?.(entityId);
    return;
  }

  // Build a Monaco IRange: single-line selection covering the raw token
  const rawLen = loc.raw?.length ?? 0;
  const range: IRange = {
    startLineNumber: loc.line,
    startColumn: loc.col,
    endLineNumber: loc.line,
    endColumn: loc.col + Math.max(rawLen, 1),
  };

  editor.revealRangeInCenter(range);
  editor.setSelection(range);
  editor.focus();
}
