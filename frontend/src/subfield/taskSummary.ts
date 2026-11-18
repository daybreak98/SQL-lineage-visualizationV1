import { rootOutputs } from './model.mjs';
import type { PathItem, Port, RecordRow, Result } from './contract';

export type Output = Port & { output?: string };
export type CheckState = 'observed' | 'not-observed' | 'unknown';
export const checkLabels: Record<CheckState, string> = {
  observed: '已看到读取', 'not-observed': '本次未见读取', unknown: '暂不能判断',
};
export const reviewBoundary = '仅供人工核查 · 行集未验证 · 不提供删除授权';
export const outputId = ({ statement, scope, slot }: Port) => JSON.stringify([statement, scope, slot]);
export const outputLabel = (output: Output) => `${output.output ?? '未命名输出'}（语句 ${output.statement} · ${output.scope} · 槽位 ${output.slot}）`;

function pathId(input: PathItem['input']) {
  return JSON.stringify([input.source, input.column, input.path_tokens ?? input.path]);
}

export function jsonBranches(paths: PathItem[]) {
  return paths.filter(({ input, uses }) => input.path !== '$' &&
    (input.path_tokens?.some(token => ['key', 'index', 'any_element'].includes(token.kind)) ?? false) &&
    (uses.length === 0 || uses.some(row => row.role !== 'REPRESENTATION')));
}

export function summarizePaths(result: Result | null, paths: PathItem[]) {
  const branches = jsonBranches(paths);
  const observed = branches.filter(branch => branch.uses.length > 0);
  const byPath = new Map<string, Output[]>();
  const linked = new Map<string, Output>();
  const counts = new Set(observed.map(path => path.id));
  for (const row of result?.mappings ?? []) {
    const output = (rootOutputs([row]) as Output[])[0];
    if (!output || !Array.isArray(row.inputs)) continue;
    for (const input of row.inputs) {
      if (!input || typeof input.source !== 'string' || typeof input.column !== 'string') continue;
      const id = pathId(input);
      if (!counts.has(id)) continue;
      const entries = byPath.get(id) ?? [];
      if (!entries.some(entry => outputId(entry) === outputId(output))) entries.push(output);
      byPath.set(id, entries);
      linked.set(outputId(output), output);
    }
  }
  return { branches, observed, byPath, outputs: [...linked.values()] };
}

export function literalKey(path: string) {
  const text = path.trim();
  // Only send identifiers with an unambiguous one-key interpretation; no path expression is sent to the service.
  return /^(?:\$\.)?([\p{L}_][\p{L}\p{N}_-]*)$/u.exec(text)?.[1] ?? null;
}

export function keyCheck(review: unknown, candidate: { source: string; column: string; key: string }): CheckState {
  if (!review || typeof review !== 'object') return 'unknown';
  const assessment = (review as RecordRow).candidate_assessment as RecordRow | undefined;
  const entries = assessment?.entries;
  if (!Array.isArray(entries)) return 'unknown';
  const matching = entries.filter(row => row?.source === candidate.source && row.column === candidate.column && row.key === candidate.key);
  if (matching.length !== 1) return 'unknown';
  if (matching[0].status === 'OBSERVED') return 'observed';
  if (matching[0].status === 'NOT_OBSERVED_NEEDS_VALIDATION') return 'not-observed';
  return 'unknown';
}

export function keyCheckReason(review: unknown, ports: Output[] = []): string | undefined {
  if (!review || typeof review !== 'object') return;
  const reason = ((review as RecordRow).candidate_assessment as RecordRow | undefined)?.reason;
  switch (reason) {
    case 'ANALYSIS_INCOMPLETE': return '分析中仍有待确认项，服务暂不能判断此键。下方已找到的读取证据仍可查看。';
    case 'PROTECTED_WHOLE_CARRIER': {
      const findings = (review as RecordRow).findings;
      const affected = Array.isArray(findings) ? ports.filter(port => findings.some(finding => {
        const reported = finding?.protected_output;
        return finding?.decision === 'RETAIN_WHOLE' && reported?.statement === port.statement &&
          reported.scope === port.scope && reported.slot === port.slot;
      })) : [];
      return '本次所选输出涉及整列依赖，当前无法对这个键给出判断。' + (affected.length
        ? `涉及输出：${affected.map(outputLabel).join('、')}。` : '涉及哪些输出尚未确认。');
    }
    case 'REQUIRES_SINGLE_SPARK_STATEMENT': return '逐键检查需要单条 Spark SQL。当前分析中已找到的读取证据仍可查看。';
    case 'PROTECTED_PATH_UNVERIFIED': return '服务未能确认所选输出的值路径，暂不能判断此键。';
    case 'COMPLEX_ROW_SEMANTICS': return '所选输出涉及复杂的行处理，服务暂不能判断此键。';
    case 'CONTROL_OR_STRUCTURAL_USE': return 'SQL 对 JSON 列存在控制或结构用途，服务暂不能判断此键。';
    case 'UNSUPPORTED_PATH': return '服务无法核实当前 SQL 的路径表达式，暂不能判断此键。';
    case 'PROTECTED_OUTPUTS_UNSPECIFIED': return '服务未确认所检查的输出，请检查范围后重试。';
  }
}
