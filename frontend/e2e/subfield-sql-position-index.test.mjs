import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { sourceExcerpt } from '../src/subfield/graph-model.mjs';
import { createSQLPositionIndex } from '../src/subfield/sqlPositionIndex.ts';

test('the synthetic text-map index preserves the recorded function and key snippets', () => {
  const { r24: { sql } } = JSON.parse(readFileSync(new URL('../src/subfield/archive-evidence-examples.json', import.meta.url), 'utf8'));
  const index = createSQLPositionIndex(sql);
  for (const [start, end, token] of [
    [81, 91, 'str_to_map'], [116, 130, "'display_mode'"],
    [181, 191, 'str_to_map'], [216, 228, "'test_group'"],
  ]) {
    const range = { start, end };
    assert.deepEqual(index.excerpt(range), sourceExcerpt(sql, range));
    assert.equal(index.excerpt(range).match, token);
    const prefix = Array.from(sql).slice(0, start).join('').split('\n');
    assert.equal(index.lineAt(start), prefix.length);
    assert.deepEqual(index.editorPosition(start), { lineNumber: prefix.length, column: prefix.at(-1).length + 1 });
  }
});

test('non-BMP code points and CRLF stay exact in excerpts and use Monaco UTF-16 columns', () => {
  const sql = 'A😀\r\n𐐷B\r\nZ';
  const index = createSQLPositionIndex(sql);
  for (const position of [{ start: 1, end: 2 }, { start: 2, end: 4 }, { start: 4, end: 5 }, { start: 8, end: 9 }]) {
    assert.deepEqual(index.excerpt(position), sourceExcerpt(sql, position));
  }
  assert.deepEqual(index.editorPosition(2), { lineNumber: 1, column: 4 });
  assert.deepEqual(index.editorPosition(3), { lineNumber: 1, column: 4 });
  assert.deepEqual(index.editorPosition(4), { lineNumber: 2, column: 1 });
  assert.deepEqual(index.editorPosition(5), { lineNumber: 2, column: 3 });
  assert.deepEqual(index.editorPosition(9), { lineNumber: 3, column: 2 });
  assert.equal(index.valid({ start: 1, end: 1 }), false);
  assert.equal(index.excerpt({ start: 8, end: 10 }), null);
});
