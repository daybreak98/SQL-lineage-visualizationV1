import type { RecordRow, Result } from './contract';

export const isUnverifiedUnionDerivation = (row: RecordRow) =>
  row?.conversion_semantics === 'UNION_COERCION_UNVERIFIED';

export const isJoinVisibilityUnverified = (row: RecordRow) =>
  row?.binding_status === 'JOIN_INPUT_VISIBILITY_UNVERIFIED';

export const isUnverifiedPhysicalRead = (row: RecordRow) =>
  isUnverifiedUnionDerivation(row) || isJoinVisibilityUnverified(row);

// Older responses flatten speculative source paths into mappings as well as uses.
// Mappings lack the occurrence witness needed to disambiguate the matching input.
export function physicalReadView<T extends Result>(result: T): T {
  const diagnostics = result.uses.filter(isUnverifiedPhysicalRead);
  if (!diagnostics.length) return result;
  const pathId = (row: RecordRow) => JSON.stringify([row?.source, row?.column, row?.path_tokens ?? row?.path]);
  const uncertain = new Map<string, Set<unknown>>();
  for (const row of diagnostics) {
    const id = pathId(row);
    if (!uncertain.has(id)) uncertain.set(id, new Set());
    uncertain.get(id)!.add(row.statement);
  }
  return {
    ...result,
    uses: result.uses.filter(row => !isUnverifiedPhysicalRead(row)),
    mappings: result.mappings.map(row => {
      if (!Array.isArray(row.inputs)) return row;
      const inputs = row.inputs.filter(input => {
        const statements = uncertain.get(pathId(input));
        return !statements || !(row.statement == null || statements.has(undefined) ||
          statements.has(null) || statements.has(row.statement));
      });
      return inputs.length === row.inputs.length ? row : { ...row, inputs };
    }),
  };
}
