import { rootOutputs } from './model.mjs';
import type { PathItem, Port, RecordRow, Result } from './contract';

export type Candidate = { source: string; column: string; key: string };
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

const noEvidence = '暂未取得可确认的证据';

export function analysisStatusText(result: Result, hasReads: boolean) {
  switch (result.coverage?.analysis_status) {
    case 'NO_ANALYZABLE_SQL': return '没有可分析的 SQL 语句';
    case 'NO_JSON_USE_IN_SCOPE': return '本次可确认的 SQL 范围内没有显式 JSON 操作';
    case 'ANALYSIS_INCOMPLETE': return hasReads
      ? '已看到部分证据，但分析尚未完成，暂不能判断完整依赖'
      : '分析未完成，暂不能判断完整依赖';
    case 'JSON_USE_OBSERVED': return '已观察到 JSON 读取';
    default: return noEvidence;
  }
}

export function pathDemandText(review: unknown) {
  const status = review && typeof review === 'object' ? (review as RecordRow).path_demand_status : undefined;
  switch (status) {
    case 'NO_ANALYZABLE_SQL': return '没有可分析的 SQL 语句';
    case 'NO_JSON_USE_IN_SCOPE': return '本次可确认范围内没有显式 JSON 操作';
    case 'ANALYSIS_INCOMPLETE': return '普通路径证明未完成';
    case 'OBSERVED': return '每个所选输出均已取得普通路径读取证据';
    default: return noEvidence;
  }
}

export function knownAnalysisReasons(result: Result) {
  const codes = new Set(result.unknowns?.map(row => row?.code));
  const reasons: string[] = [];
  if (codes.has('PARSE_ERROR')) reasons.push('部分 SQL 未能解析');
  if (codes.has('JOIN_INPUT_VISIBILITY_UNVERIFIED')) reasons.push('有 JOIN ON 读取无法确认引用关系在当前连接中可见');
  if (codes.has('UNSUPPORTED_JSON_PATH')) reasons.push('有动态或无法核实的 JSON 路径');
  if (codes.has('UNBOUND_COLUMN') || codes.has('AMBIGUOUS_COLUMN') || codes.has('UNSUPPORTED_SOURCE') ||
      codes.has('UNKNOWN_JSON_INPUT')) reasons.push('有未绑定或无法确认来源的列');
  if (Array.isArray(result.opaque_call_arguments) && result.opaque_call_arguments.length) {
    reasons.push('有不透明函数或 UDF，内部依赖未核实');
  }
  return reasons;
}

export function literalKey(path: string) {
  const text = path.trim();
  // Only send identifiers with an unambiguous one-key interpretation; no path expression is sent to the service.
  return /^(?:\$\.)?([\p{L}_][\p{L}\p{N}_-]*)$/u.exec(text)?.[1] ?? null;
}

function exactCandidateEntry(review: unknown, candidate: Candidate): RecordRow | undefined {
  if (!review || typeof review !== 'object') return;
  const assessment = (review as RecordRow).candidate_assessment as RecordRow | undefined;
  const entries = assessment?.entries;
  if (!Array.isArray(entries)) return;
  const matches = entries.filter(row => row?.source === candidate.source && row.column === candidate.column && row.key === candidate.key);
  return matches.length === 1 ? matches[0] : undefined;
}

export function keyCheck(review: unknown, candidate: Candidate): CheckState {
  const entry = exactCandidateEntry(review, candidate);
  if (entry?.status === 'OBSERVED') return 'observed';
  if (entry?.status === 'NOT_OBSERVED_NEEDS_VALIDATION') return 'not-observed';
  return 'unknown';
}

export function keyCheckReason(review: unknown, ports: Output[] = [], candidate?: Candidate): string | undefined {
  const entry = candidate && exactCandidateEntry(review, candidate);
  if (entry?.status === 'UNKNOWN') {
    if (entry.reason === 'SOURCE_NAME_CASE_MISMATCH_UNVERIFIED') return '源名大小写与已观测的拼写不同；尚未确认是否同一数据源。';
    if (entry.reason === 'SOURCE_NAME_CASE_AMBIGUOUS') return 'SQL 中存在多个仅大小写不同的源名，无法确认候选对应哪个。';
  }
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
    case 'PROJECTION_SCOPE_NOT_CLOSED': return '所检查的 SQL 中，有输出项尚未完成解析，暂不能判断此键是否未被读取。';
    case 'PROTECTED_PATH_UNVERIFIED': return '服务未能确认所选输出的值路径，暂不能判断此键。';
    case 'COMPLEX_ROW_SEMANTICS': return '所选输出涉及复杂的行处理，服务暂不能判断此键。';
    case 'CONTROL_OR_STRUCTURAL_USE': return 'SQL 对 JSON 列存在控制或结构用途，服务暂不能判断此键。';
    case 'UNSUPPORTED_PATH': return '服务无法核实当前 SQL 的路径表达式，暂不能判断此键。';
    case 'PROTECTED_OUTPUTS_UNSPECIFIED': return '服务未确认所检查的输出，请检查范围后重试。';
  }
}
