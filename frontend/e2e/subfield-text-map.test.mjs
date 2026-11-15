import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { sourceExcerpt } from '../src/subfield/graph-model.mjs';
import { layeredSQL, textMapSQL } from '../src/subfield/workbench.mjs';
import { isTextMapEvidence, textMapLocations, textMapTitle } from '../src/subfield/textMapEvidence.ts';
import { buildEvidenceBundle } from '../src/subfield/evidenceBundle.ts';

test('synthetic SELECT and WHERE map facts retain separate function and key locations', async () => {
  const sql = textMapSQL;
  const input = { role: 'REPRESENTATION', source: 'demo.events', column: 'attributes', function_binding: 'UNVERIFIED' };
  const position = (start, token) => ({ start, end: start + token.length });
  const select = { ...input, clause: 'SELECT', map_key: 'category',
    position: position(sql.indexOf('str_to_map'), 'str_to_map'), map_key_position: position(sql.indexOf("'category'"), "'category'") };
  const where = { ...input, clause: 'WHERE', map_key: 'region',
    position: position(sql.lastIndexOf('str_to_map'), 'str_to_map'), map_key_position: position(sql.indexOf("'region'"), "'region'") };
  const original = JSON.stringify([select, where]);
  assert.deepEqual([select, where, { ...where, role: 'CONDITION' }].filter(isTextMapEvidence), [select, where]);
  assert.match(textMapTitle(select), /SELECT.*attributes.*category.*函数身份未核/);
  assert.match(textMapTitle(where), /WHERE.*attributes.*region.*函数身份未核/);
  for (const fact of [select, where]) {
    assert.deepEqual(textMapLocations(fact).map(({ position }) => sourceExcerpt(sql, position)?.match),
      ['str_to_map', `'${fact.map_key}'`]);
  }
  assert.equal(textMapLocations({ ...where, map_key_position: null })[1].position, null);
  assert.equal(JSON.stringify([select, where]), original);
  const bundle = await buildEvidenceBundle({
    requestId: 'demo-map', capturedAt: '2026-11-16T00:00:00+08:00',
    request: { sql, dialect: 'hive' }, origin: { kind: 'EXCERPT' },
    rawResponse: { uses: [select, where], coverage: { dialect: 'hive', sql_sha256: createHash('sha256').update(sql).digest('hex') } },
  });
  assert.deepEqual(bundle.response.uses, [select, where]);
  assert.deepEqual(bundle.locations.find(location => location.fact_ref === '/uses/1/map_key_position')?.request_span,
    { unit: 'UNICODE_CODE_POINT', ...where.map_key_position });
  const context = '合成示例 · 仅分析本次提交 SQL';
  const reduced = await buildEvidenceBundle({
    requestId: 'demo-layered', capturedAt: bundle.captured_at,
    request: { sql: layeredSQL, dialect: 'spark' },
    rawResponse: { uses: [{ position: { start: 0, end: 1 } }],
      coverage: { dialect: 'spark', sql_sha256: createHash('sha256').update(layeredSQL).digest('hex') } },
    origin: { kind: 'CONSTRUCTED', context },
  });
  assert.deepEqual(reduced.origin, { kind: 'CONSTRUCTED', verification: 'NOT_APPLICABLE', context });
  assert.ok(reduced.locations.every(location => location.original_span === null));
});
