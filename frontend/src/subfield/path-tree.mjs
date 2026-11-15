const array = value => Array.isArray(value) ? value : [];
const identity = input => JSON.stringify([input?.source, input?.column, input?.path_tokens ?? input?.path]);
const bound = input => input?.source && input.column && typeof input.path === 'string';

export function pathTree(result) {
  const index = new Map();
  const add = (input, use) => {
    if (!bound(input)) return;
    const id = identity(input);
    if (!index.has(id)) index.set(id, { id, input, uses: [] });
    if (use) index.get(id).uses.push(use);
  };
  for (const row of array(result?.uses)) add(row, row);
  for (const row of array(result?.mappings)) for (const input of array(row.inputs)) add(input);
  return [...index.values()];
}

export function projectPath(result, item) {
  if (!item) return { ...result, uses: [], mappings: [], unknowns: [] };
  const matches = input => bound(input) && identity(input) === item.id;
  const port = row => JSON.stringify([row.statement, row.scope, row.slot]);
  const ports = new Map();
  for (const mapping of result.mappings) {
    const key = port(mapping);
    ports.set(key, ports.has(key) ? null : mapping);
  }
  const chosen = new Map();
  const queue = result.mappings.filter(mapping => array(mapping.inputs).some(matches));
  for (const mapping of queue) chosen.set(mapping, []);
  for (let i = 0; i < queue.length; i++) {
    const consumer = queue[i];
    const eligible = array(consumer.port_reads).filter(read => {
      if (!read.producer || read.producer.statement !== consumer.statement) return false;
      const producer = ports.get(port(read.producer));
      return producer && (array(producer.inputs).some(matches) ||
        (read.kind === 'EXTRACT' && JSON.stringify(read.path_tokens) === JSON.stringify(item.input.path_tokens) &&
          array(producer.inputs).some(input => input.source === item.input.source && input.column === item.input.column && input.path === '$')) ||
        (array(consumer.inputs).some(input => input.source === item.input.source && input.column === item.input.column && input.path === '$') &&
          read.kind === 'PASSTHROUGH' && array(producer.inputs).some(input => input.source === item.input.source && input.column === item.input.column && input.path === '$')));
    });
    chosen.set(consumer, eligible);
    for (const read of eligible) {
      const producer = ports.get(port(read.producer));
      if (!chosen.has(producer)) { chosen.set(producer, []); queue.push(producer); }
    }
  }
  return {
    ...result, uses: item.uses, unknowns: [],
    mappings: [...chosen].map(([mapping, port_reads]) => ({ ...mapping, port_reads })),
  };
}
