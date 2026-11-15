import type { Port, RecordRow, Result } from './contract';
export function normalize(input: unknown): Result;
export function parseSourceSchemas(text: string): Record<string, unknown> | undefined;
export function rootOutputs(mappings: RecordRow[]): (Port & { output?: string })[];
