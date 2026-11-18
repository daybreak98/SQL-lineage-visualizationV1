const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);

export const format = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2) ?? '';

export function normalize(value) {
  if (!isRecord(value) || !['uses', 'mappings'].every(key => Array.isArray(value[key])) ||
      (value.unknowns !== undefined && !Array.isArray(value.unknowns))) {
    throw new Error('响应缺少 uses 或 mappings 数组，或 unknowns 格式无效。');
  }
  const groups = new Map();
  value.uses.forEach((row, index) => {
    const { source, column, path } = row ?? {};
    const identity = JSON.stringify([source ?? null, column ?? null, path ?? null]);
    if (!groups.has(identity)) {
      groups.set(identity, {
        id: String(groups.size), source: source ?? null, column: column ?? null,
        path: path ?? null, records: [],
      });
    }
    groups.get(identity).records.push({ row, index });
  });
  return { ...value, paths: [...groups.values()] };
}

export function parseSourceSchemas(text) {
  if (!text.trim()) return undefined;
  let schemas;
  try {
    schemas = JSON.parse(text);
  } catch {
    throw new Error('源列清单不是有效的 JSON。');
  }
  if (!isRecord(schemas)) {
    throw new Error('源列清单须为以表名为键的 JSON 对象。');
  }
  return schemas;
}

export function rootOutputs(mappings) {
  const outputs = new Map();
  for (const row of mappings) {
    if (row?.root !== true || !Number.isInteger(row.statement) ||
        typeof row.scope !== 'string' || !row.scope || !Number.isInteger(row.slot)) continue;
    const { statement, scope, slot, output } = row;
    const identity = JSON.stringify([statement, scope, slot]);
    if (!outputs.has(identity)) outputs.set(identity, { statement, scope, slot, output });
  }
  return [...outputs.values()];
}
