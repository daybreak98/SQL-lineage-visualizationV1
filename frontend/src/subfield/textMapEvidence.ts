import type { Position, RecordRow } from './contract';

type TextMapRow = RecordRow & { map_key: string };
type Location = { label: string; position?: Position | null };

export function isTextMapEvidence(row: RecordRow): row is TextMapRow {
  return row.role === 'REPRESENTATION' && typeof row.map_key === 'string';
}

export function textMapTitle(row: TextMapRow): string {
  const clause = typeof row.clause === 'string' ? row.clause : '子句未记录';
  const source = typeof row.source === 'string' ? row.source : '来源未绑定';
  const column = typeof row.column === 'string' ? row.column : '列未绑定';
  const binding = row.function_binding === 'UNVERIFIED' ? '函数身份未核'
    : typeof row.function_binding === 'string' ? `函数身份：${row.function_binding}` : '函数身份未提供';
  return `${clause} · ${source}.${column} · 键 ${JSON.stringify(row.map_key)} · ${binding}`;
}

function readPosition(value: unknown): Position | null {
  if (!value || typeof value !== 'object' || !('start' in value) || !('end' in value)) return null;
  const { start, end } = value;
  return typeof start === 'number' && typeof end === 'number' ? { start, end } : null;
}

export function textMapLocations(row: TextMapRow): Location[] {
  return [
    { label: '函数 token', position: row.position },
    { label: '键 token', position: readPosition(row.map_key_position) },
  ];
}
