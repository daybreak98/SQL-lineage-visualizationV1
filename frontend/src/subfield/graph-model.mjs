const identity = parts => JSON.stringify(parts);

export function graphFacts(result) {
  const nodes = new Map();
  const edges = new Map();
  const addNode = (key, lane, label, uncertain, evidence, priority = 0) => {
    if (!nodes.has(key)) nodes.set(key, { key, lane, label, uncertain, priority, evidence: new Set() });
    if (evidence) nodes.get(key).evidence.add(evidence);
    return key;
  };
  const addEdge = (from, to, uncertain, row) => {
    const key = identity([from, to]);
    if (!edges.has(key)) edges.set(key, { from, to, uncertain, evidence: new Set() });
    if (row) edges.get(key).evidence.add(row);
    edges.get(key).uncertain ||= uncertain;
  };
  const origin = (input, row) => {
    const source = input?.source || null;
    const column = input?.column || null;
    const path = input?.path ?? null;
    const uncertain = !source || !column || typeof path !== 'string';
    const table = addNode(identity(['table', source]), 0, source ?? '来源未绑定', !source, row);
    const key = addNode(identity(['path', source, column, path, input?.path_tokens ?? null]), 1,
      `${column ?? '列未绑定'} · ${path ?? '路径未确定'}`, uncertain, row,
      path === '$' ? 2 : uncertain ? 1 : 0);
    addEdge(table, key, uncertain, row);
    return { key, uncertain };
  };
  for (const row of result.uses) origin(row, row);
  result.mappings.forEach((row, index) => {
    if (!row) return;
    const uncertain = row.kind === 'UNKNOWN';
    const projection = addNode(identity(['projection', row.statement, row.scope, row.slot, index]), 2,
      [row.target, row.output || `槽位 ${row.slot ?? '?'}`, row.scope].filter(Boolean).join(' · '),
      uncertain, row, row.root === true ? 0 : 1);
    for (const input of Array.isArray(row.inputs) ? row.inputs : []) {
      const path = origin(input, row);
      addEdge(path.key, projection, uncertain || path.uncertain, row);
    }
  });
  for (const [index, row] of result.unknowns.entries()) {
    addNode(identity(['unknown', index]), 3, row?.code || `未决 #${index + 1}`, true, row);
  }
  return { nodes: [...nodes.values()].sort((a, b) => a.lane - b.lane || a.priority - b.priority), edges: [...edges.values()] };
}

// SQLGlot offsets count Unicode code points; convert to browser string offsets.
export function sourceExcerpt(sql, position) {
  const { start, end } = position ?? {};
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || start >= end) return null;
  const chars = Array.from(sql);
  if (end > chars.length) return null;
  const lineStart = start === 0 ? -1 : chars.lastIndexOf('\n', start - 1);
  const lineEnd = chars.indexOf('\n', end);
  return {
    before: chars.slice(Math.max(lineStart + 1, start - 180), start).join(''),
    match: chars.slice(start, end).join(''),
    after: chars.slice(end, Math.min(lineEnd < 0 ? chars.length : lineEnd, end + 180)).join(''),
  };
}
