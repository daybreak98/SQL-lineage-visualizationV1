import type { PathItem, Result } from './contract';
export function pathTree(result: Result | null): PathItem[];
export function projectPath(result: Result, item: PathItem): Result;
