import type { Position, RecordRow } from './contract';
import type { createSQLPositionIndex } from './sqlPositionIndex';

export function jsonReadLocation(row: RecordRow, index: Pick<ReturnType<typeof createSQLPositionIndex>, 'valid'> | null): Position | null {
  const raw = row.json_path_position;
  if (row.kind !== 'EXTRACT' || raw === null || typeof raw !== 'object' ||
      !('start' in raw) || !('end' in raw) || typeof raw.start !== 'number' || typeof raw.end !== 'number') return null;
  const position = { start: raw.start, end: raw.end };
  return index?.valid(position) ? position : null;
}
