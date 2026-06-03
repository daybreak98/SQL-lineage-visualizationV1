import type { SourceLocation } from '../../types/lineage';
import type { editor as monacoEditor, IDisposable } from 'monaco-editor';

// ── Types ────────────────────────────────────────────────

export interface CursorMatchResult {
  entityId: string;
  location: SourceLocation;
}

// ── Cursor → SourceLocation matching ────────────────────

/**
 * Match a Monaco cursor position (1-based line/column) against the
 * source_locations lookup. Returns the entity_id whose SourceLocation
 * is closest to the cursor on the same line.
 *
 * Matching rules:
 * - Only considers SourceLocations on the same line as the cursor.
 * - Requires cursor column >= SourceLocation column (cursor after or at).
 * - Picks the nearest SourceLocation by column distance.
 */
export function matchCursorToSourceLocation(
  line: number,
  column: number,
  sourceLocations: Record<string, SourceLocation> | undefined | null,
): CursorMatchResult | null {
  if (!sourceLocations) return null;

  let bestMatch: CursorMatchResult | null = null;
  let bestDist = Infinity;

  for (const entry of Object.values(sourceLocations)) {
    if (entry.line === line && column >= entry.col) {
      const dist = column - entry.col;
      if (dist < bestDist) {
        bestDist = dist;
        bestMatch = { entityId: entry.entityId, location: entry };
      }
    }
  }

  return bestMatch;
}

// ── Monaco cursor listener factory ──────────────────────

/**
 * Creates a cursor position change handler for the Monaco editor.
 * When the user moves the cursor, it matches the position against
 * source_locations and calls onEntityChange with the matched entityId
 * (or null if nothing matches).
 *
 * The handler reads sourceLocations and onEntityChange from the
 * provided refs so it always uses the latest values without needing
 * to re-register listeners.
 */
export function createCursorHandler(
  sourceLocsRef: { current: Record<string, SourceLocation> | undefined | null },
  onEntityChangeRef: { current: ((entityId: string | null) => void) | undefined },
) {
  return (editor: monacoEditor.IStandaloneCodeEditor): IDisposable => {
    return editor.onDidChangeCursorPosition((e) => {
      const match = matchCursorToSourceLocation(
        e.position.lineNumber,
        e.position.column,
        sourceLocsRef.current ?? undefined,
      );
      onEntityChangeRef.current?.(match?.entityId ?? null);
    });
  };
}
