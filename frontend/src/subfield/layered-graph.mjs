const portKey = port => Number.isInteger(port?.statement) && typeof port.scope === 'string' &&
  port.scope && Number.isInteger(port.slot) ? JSON.stringify([port.statement, port.scope, port.slot]) : null;

export function layeredGraphFacts(result) {
  const nodes = new Map(), edges = [], ports = new Map(), sourceEdges = new Map();
  const add = (key, lane, label, row, uncertain = false) => {
    if (!nodes.has(key)) nodes.set(key, { key, lane, label, uncertain, evidence: new Set() });
    nodes.get(key).evidence.add(row);
    return nodes.get(key);
  };
  const link = (from, to, row) => edges.push({ from, to, uncertain: false, evidence: new Set([row]) });
  const mappings = result.mappings.flatMap((row, index) => {
    const id = portKey(row);
    if (!id) return [];
    const key = `port:${index}`;
    ports.set(id, ports.has(id) ? null : { key, row });
    const node = add(key, 2, `${row.root === true ? '根输出' : '投影端口'} · ${row.output || '未命名'} · ${row.statement}/${row.scope}/${row.slot}`, row);
    node.display = row.output || '未命名';
    node.root = row.root === true;
    return [{ key, id, row }];
  });
  for (const { key, id, row } of mappings) {
    const node = nodes.get(key);
    if (!ports.get(id)) { node.uncertain = true; continue; }
    const reads = Array.isArray(row.port_reads) ? row.port_reads : [];
    if (reads.length) {
      for (const read of reads) {
        const producer = ports.get(portKey(read?.producer));
        if (!producer || producer.key === key || producer.row.root !== false ||
            producer.row.statement !== row.statement || !read.position) {
          node.uncertain = true;
          continue;
        }
        link(producer.key, key, read);
      }
      continue;
    }
    const origin = Array.isArray(row.inputs) && row.inputs.length === 1 ? row.inputs[0] : null;
    if (row.terminal_binding !== 'SQL_NAMED_RELATION_COLUMN' || !origin?.source || !origin.column) {
      node.uncertain = true;
      continue;
    }
    const table = JSON.stringify(['table', origin.source]);
    const column = JSON.stringify(['column', origin.source, origin.column]);
    add(table, 0, origin.source, row);
    add(column, 1, origin.column, row);
    if (!sourceEdges.has(column)) {
      link(table, column, row);
      sourceEdges.set(column, edges.at(-1));
    } else {
      sourceEdges.get(column).evidence.add(row);
    }
    link(column, key, row);
  }
  // Assign levels only from explicit evidence. A cycle cannot establish a layer.
  const pending = new Map([...nodes.keys()].map(key => [key, 0]));
  const outgoing = new Map();
  for (const edge of edges) {
    pending.set(edge.to, pending.get(edge.to) + 1);
    if (!outgoing.has(edge.from)) outgoing.set(edge.from, []);
    outgoing.get(edge.from).push(edge);
  }
  const queue = [...pending].filter(([, count]) => count === 0).map(([key]) => key);
  for (let i = 0; i < queue.length; i++) {
    for (const edge of outgoing.get(queue[i]) ?? []) {
      const target = nodes.get(edge.to);
      target.lane = Math.max(target.lane, nodes.get(edge.from).lane + 1);
      const count = pending.get(edge.to) - 1;
      pending.set(edge.to, count);
      if (count === 0) queue.push(edge.to);
    }
  }
  for (const [key, count] of pending) if (count) nodes.get(key).uncertain = true;
  const lastLane = [...nodes.values()].reduce((max, node) => Math.max(max, node.lane), 2);
  result.unknowns.forEach((row, index) => {
    add(`unknown:${index}`, lastLane + 1, row?.code || `未决 #${index + 1}`, row, true).kind = 'unknown';
  });
  return {
    nodes: [...nodes.values()].sort((a, b) => a.lane - b.lane),
    edges: edges.filter(edge => !pending.get(edge.from) && !pending.get(edge.to)),
    lanes: Array.from({ length: lastLane + (result.unknowns.length ? 2 : 1) }, (_, index) =>
      index === 0 ? '源关系' : index === 1 ? '源列' : index > lastLane ? '未决记录' : `投影端口 · 第 ${index - 1} 层`),
  };
}
