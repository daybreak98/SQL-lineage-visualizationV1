import type { Graph, Position, Result } from './contract';
export function graphFacts(result: Result): Graph;
export function sourceExcerpt(sql: string, position?: Position | null): {before: string; match: string; after: string} | null;
