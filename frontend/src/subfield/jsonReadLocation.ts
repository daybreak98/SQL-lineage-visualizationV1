import type { Position, RecordRow } from './contract';
import type { createSQLPositionIndex } from './sqlPositionIndex';

type PositionValidator = Pick<ReturnType<typeof createSQLPositionIndex>, 'valid'>;

export function jsonReadLocation(row: RecordRow, index: PositionValidator | null): Position | null {
  const raw = row.json_path_position;
  if (row.kind !== 'EXTRACT' || raw === null || typeof raw !== 'object' ||
      !('start' in raw) || !('end' in raw) || typeof raw.start !== 'number' || typeof raw.end !== 'number') return null;
  const position = { start: raw.start, end: raw.end };
  return index?.valid(position) ? position : null;
}

export function preferredJsonReadLocation(rows: readonly RecordRow[], index: PositionValidator | null):
  { kind: 'literal' | 'call'; position: Position } | null {
  if (!index) return null;
  let fallback: Position | null = null;
  for (const row of rows) {
    const literal = jsonReadLocation(row, index);
    if (literal) return { kind: 'literal', position: literal };
    if (!fallback && index.valid(row.position)) fallback = row.position;
  }
  return fallback ? { kind: 'call', position: fallback } : null;
}
