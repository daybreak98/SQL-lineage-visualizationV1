import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createSQLPositionIndex } from '../src/subfield/sqlPositionIndex.ts';
import { jsonReadLocation } from '../src/subfield/jsonReadLocation.ts';

test('the two COALESCE branches preserve carrier locations and only use explicit valid JSON literal spans', () => {
  const sql = "WITH base AS (SELECT t.j FROM src t), l AS (SELECT get_json_object(x.j,'$.a') AS a FROM base x), r AS (SELECT get_json_object(x.j,'$.b') AS b FROM base x) SELECT COALESCE(l.a,r.b) AS protected FROM l CROSS JOIN r";
  const source = createSQLPositionIndex(sql);
  const port = scope => ({ statement: 1, scope, slot: 1 });
  for (const [slot, key, mid, argument, carrier, literal] of [[1, 'a', '1:2', 173, 69, 71], [2, 'b', '1:3', 177, 128, 130]]) {
    const edges = [
      { kind: 'COALESCE_INPUT', argument_slot: slot, consumer: port('1:4'), producer: port(mid),
        position: { start: argument, end: argument + 1 } },
      { kind: 'EXTRACT', consumer: port(mid), producer: port('1:1'), path_tokens: [{ kind: 'key', value: key }],
        position: { start: carrier, end: carrier + 1 }, json_path_position: { start: literal, end: literal + 5 } },
    ];
    assert.equal(source.excerpt(edges[1].position).match, 'j');
    assert.equal(source.excerpt(jsonReadLocation(edges[1], source)).match, `'$.${key}'`);
    assert.equal(jsonReadLocation({ ...edges[0], json_path_position: edges[1].json_path_position }, source), null);
    assert.equal(jsonReadLocation({ ...edges[1], json_path_position: undefined }, source), null);
    assert.equal(jsonReadLocation({ ...edges[1], json_path_position: { start: literal, end: sql.length + 1 } }, source), null);
  }
});
