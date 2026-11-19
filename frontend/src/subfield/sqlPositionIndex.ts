import type { Position } from './contract';

const contextLimit = 180;

/** Index one submitted SQL string; service spans are half-open Unicode code-point ranges. */
export function createSQLPositionIndex(sql: string) {
  const utf16Offsets = [0];
  const lineAtPoint = [0];
  const lineStarts = [0];
  const lineFeeds: number[] = [];
  let utf16 = 0;
  let line = 0;

  for (const char of sql) {
    const point = utf16Offsets.length - 1;
    utf16 += char.length;
    if (char === '\n') {
      lineFeeds.push(point);
      lineStarts.push(point + 1);
      line++;
    }
    utf16Offsets.push(utf16);
    lineAtPoint.push(line);
  }
  const length = utf16Offsets.length - 1;
  const hasOffset = (offset: number) => Number.isInteger(offset) && 0 <= offset && offset <= length;
  const valid = (position?: Position | null): position is Position =>
    position != null && hasOffset(position.start) && hasOffset(position.end) && position.start < position.end;
  const slice = (start: number, end: number) => sql.slice(utf16Offsets[start], utf16Offsets[end]);

  return {
    valid,
    utf16Offset(offset: number) { return hasOffset(offset) ? utf16Offsets[offset] : null; },
    excerpt(position?: Position | null) {
      if (!valid(position)) return null;
      const { start, end } = position;
      const left = Math.max(lineStarts[lineAtPoint[start]], start - contextLimit);
      const right = Math.min(lineFeeds[lineAtPoint[end]] ?? length, end + contextLimit);
      return { before: slice(left, start), match: slice(start, end), after: slice(end, right) };
    },
    lineAt(offset: number) {
      return hasOffset(offset) ? lineAtPoint[offset] + 1 : null;
    },
    editorPosition(offset: number) {
      if (!hasOffset(offset)) return null;
      const row = lineAtPoint[offset];
      let end = utf16Offsets[offset];
      // A boundary between CR and LF has no separate column in a Monaco line.
      if (lineFeeds[row] === offset && sql.charCodeAt(end - 1) === 13) end--;
      return { lineNumber: row + 1, column: end - utf16Offsets[lineStarts[row]] + 1 };
    },
  };
}
