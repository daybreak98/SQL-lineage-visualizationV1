import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { sourceExcerpt } from '../src/subfield/graph-model.mjs';
import { isTextMapEvidence, textMapLocations, textMapTitle } from '../src/subfield/textMapEvidence.ts';
import { buildEvidenceBundle } from '../src/subfield/evidenceBundle.ts';

test('the synthetic SELECT and WHERE map facts retain separate function and key locations', async () => {
  const { r24: { sql } } = JSON.parse(readFileSync(new URL('../src/subfield/archive-evidence-examples.json', import.meta.url), 'utf8'));
  const input = { role: 'REPRESENTATION', source: 'demo.widget_events', column: 'attributes', function_binding: 'UNVERIFIED' };
  const select = { ...input, clause: 'SELECT', map_key: 'display_mode',
    position: { start: 81, end: 91 }, map_key_position: { start: 116, end: 130 } };
  const where = { ...input, clause: 'WHERE', map_key: 'test_group',
    position: { start: 181, end: 191 }, map_key_position: { start: 216, end: 228 } };
  const original = JSON.stringify([select, where]);
  assert.deepEqual([select, where, { ...where, role: 'CONDITION' }].filter(isTextMapEvidence), [select, where]);
  assert.match(textMapTitle(select), /SELECT.*attributes.*display_mode.*函数身份未核/);
  assert.match(textMapTitle(where), /WHERE.*attributes.*test_group.*函数身份未核/);
  for (const fact of [select, where]) {
    assert.deepEqual(textMapLocations(fact).map(({ position }) => sourceExcerpt(sql, position)?.match),
      ['str_to_map', `'${fact.map_key}'`]);
  }
  assert.equal(textMapLocations({ ...where, map_key_position: null })[1].position, null);
  assert.equal(JSON.stringify([select, where]), original);
  const bundle = await buildEvidenceBundle({
    requestId: 'synthetic-text-map', capturedAt: '2026-11-16T00:00:00+08:00',
    request: { sql, dialect: 'hive' }, origin: { kind: 'EXCERPT' },
    rawResponse: { uses: [select, where], coverage: { dialect: 'hive', sql_sha256: createHash('sha256').update(sql).digest('hex') } },
  });
  assert.deepEqual(bundle.response.uses, [select, where]);
  assert.deepEqual(bundle.locations.find(location => location.fact_ref === '/uses/1/map_key_position')?.request_span,
    { unit: 'UNICODE_CODE_POINT', start: 216, end: 228 });
  const context = '合成精简查询 · 仅定位提交 SQL';
  const archive = JSON.parse(readFileSync(new URL('../src/subfield/archive-example.json', import.meta.url), 'utf8'));
  const reduced = await buildEvidenceBundle({
    requestId: 'synthetic-single-table', capturedAt: bundle.captured_at,
    request: { sql: archive.sql, dialect: archive.parser_dialect },
    rawResponse: { uses: [{ position: { start: 0, end: 1 } }],
      coverage: { dialect: archive.parser_dialect, sql_sha256: createHash('sha256').update(archive.sql).digest('hex') } },
    origin: { kind: 'CONSTRUCTED', context },
  });
  assert.deepEqual(reduced.origin, { kind: 'CONSTRUCTED', verification: 'NOT_APPLICABLE', context });
  assert.ok(reduced.locations.every(location => location.original_span === null));
});
