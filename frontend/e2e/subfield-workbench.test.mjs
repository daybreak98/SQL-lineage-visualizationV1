import assert from 'node:assert/strict';
import test from 'node:test';
import { normalize } from '../src/subfield/model.mjs';
import { layeredGraphFacts } from '../src/subfield/layered-graph.mjs';

test('layered graph follows explicit reads and stops at unmarked or ambiguous endpoints', () => {
  const port = (scope, slot = 1) => ({ statement: 1, scope, slot });
  const input = { source: 'db.events', column: 'payload', path: '$', path_tokens: [] };
  const read = scope => ({ producer: port(scope), kind: 'PASSTHROUGH', position: { start: 1, end: 2 } });
  const terminal = { ...port('a'), output: 'payload', root: false, terminal_binding: 'SQL_NAMED_RELATION_COLUMN', inputs: [input] };
  const inner = { ...port('b'), output: 'id', root: false, port_reads: [read('a')], inputs: [input] };
  const root = { ...port('c'), output: 'id', root: true, port_reads: [read('b')], inputs: [input] };
  const graph = layeredGraphFacts({ mappings: [root, inner, terminal], unknowns: [] });
  assert.deepEqual(graph.nodes.map(node => node.lane), [0, 1, 2, 3, 4]);
  assert.equal(graph.edges.length, 4);
  assert.equal(graph.edges.filter(edge => edge.evidence.has(inner.port_reads[0])).length, 1);
  const missing = layeredGraphFacts({ mappings: [root, { ...inner, port_reads: undefined }, { ...terminal, terminal_binding: undefined }], unknowns: [] });
  assert.equal(missing.edges.length, 1);
  assert.equal(missing.nodes.filter(node => node.uncertain).length, 2);
  const ambiguous = layeredGraphFacts({ mappings: [root, inner, { ...inner }, terminal], unknowns: [] });
  assert.equal(ambiguous.edges.length, 2);
});

test('keeps distinct paths, repeat evidence and unbound uses', () => {
  const a = { source: 'events', column: 'payload', path: '$.PhotoId', role: 'VALUE' };
  const uses = [a, { ...a, role: 'CONDITION' }, { ...a, path: '$.photoid' }, { path: null }];
  const result = normalize({ uses, mappings: [], unknowns: [], coverage: { complete: false } });
  assert.deepEqual(result.paths.map(p => p.records.length), [2, 1, 1]);
  assert.equal(result.paths[2].records[0].row, uses[3]);
  assert.throws(() => normalize({ error: 'not a result' }), /响应/);
});
