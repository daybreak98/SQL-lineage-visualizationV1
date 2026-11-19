import { useState } from 'react';
import type { ReactNode } from 'react';
import type { RecordRow, Result } from './contract';
import { isUnverifiedPhysicalRead } from './unverifiedUnion';
import { isTextMapEvidence, textMapTitle } from './textMapEvidence';

type PickEvidence = (title: string, rows: RecordRow[]) => void;
type PreviewEvidence = (title: string, rows: RecordRow[]) => ReactNode;
const record = (value: unknown): RecordRow | undefined =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as RecordRow : undefined;
const records = (value: unknown): RecordRow[] | undefined =>
  Array.isArray(value) ? value.flatMap(item => { const row = record(item); return row ? [row] : []; }) : undefined;
const text = (value: unknown, fallback = '未提供') =>
  typeof value === 'string' && value ? value : typeof value === 'number' ? String(value) : fallback;
const roleLabels: Record<string, string> = {
  ERROR: '错误行为', CONDITION: '条件依赖', RELATIONAL: '关系依赖', STRUCTURE: '结构依赖', REPRESENTATION: '原始表示依赖',
};
const outcomes: Record<string, string> = {
  RETAIN_WHOLE: '保留整包', NEEDS_PROOF: '仍需验证', OBSERVED: '已观察到依赖',
  NOT_OBSERVED_NEEDS_VALIDATION: '待验证', UNKNOWN: '证据不足', UNRESOLVED: '未决',
};
const name = (labels: Record<string, string>, value: unknown) =>
  typeof value === 'string' && Object.hasOwn(labels, value) ? labels[value] : text(value);
const portLabel = (value: unknown) => {
  const port = record(value);
  return port ? `语句 ${text(port.statement)} / 作用域 ${text(port.scope)} / 槽位 ${text(port.slot)}` : '端口未提供';
};
function pathLabel(value: unknown) {
  const tokens = records(value);
  if (!tokens) return '路径未提供';
  return '$' + tokens.map(({ kind, value: token }) => kind === 'key' ? `[${JSON.stringify(token)}]`
    : kind === 'index' ? `[${text(token)}]` : `{${text(kind)}${token == null ? '' : ':' + JSON.stringify(token)}}`).join('');
}
const sourceLabel = (row: RecordRow) => `${text(row.source, '来源未提供')} · ${text(row.column, '列未提供')}`;

interface Entry { title: string; evidence?: RecordRow[] }
function Report({ title, rows, describe, pick, preview }: {
  title: string; rows: RecordRow[] | undefined; describe: (row: RecordRow) => Entry; pick: PickEvidence; preview?: PreviewEvidence;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  if (rows === undefined) return <p>{title}：服务未提供。</p>;
  if (!rows.length) return <p>{title}：0 项（服务返回空列表）。</p>;
  const row = selected === null ? undefined : rows[selected];
  const current = open && preview && row ? describe(row) : undefined;
  return <details onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>{title} · {rows.length} 项</summary>
    {open && <ul>{rows.map((row, i) => {
      const entry = describe(row);
      return <li key={i}><button type="button" aria-pressed={preview ? i === selected : undefined}
        onClick={() => {
          if (preview) setSelected(i);
          else pick(entry.title, entry.evidence ?? [row]);
        }}>{entry.title}</button></li>;
    })}</ul>}
    {current && preview && row && <div className="report-evidence">
      <p className="report-current" role="status">当前证据：{current.title}</p>
      {preview(current.title, current.evidence ?? [row])}
    </div>}
  </details>;
}
const unknown = (row: RecordRow): Entry => ({ title: [text(row.code, '未决记录'), text(row.message ?? row.expression, '')].filter(Boolean).join(' · ') });

export function AnalysisReports({ result, pick, preview }: { result: Result; pick: PickEvidence; preview?: PreviewEvidence }) {
  const textMapReads = result.uses.filter(isTextMapEvidence);
  return <div className="subfield-report-list">
    {textMapReads.length > 0 && <Report title="文本 Map 查键" rows={textMapReads} pick={pick} preview={preview}
      describe={row => ({ title: isTextMapEvidence(row) ? textMapTitle(row) : '文本 Map 查键' })} />}
    <Report title="传播映射" rows={result.mappings} pick={pick} describe={row => ({
      title: `${text(row.output, '未命名输出')} · ${portLabel(row)}`,
    })} />
    <Report title="生成器／行集依赖" rows={records(result.generators)} pick={pick} preview={preview} describe={row => ({
      title: [text(row.function, '生成器'), text(row.mode, '模式未提供'),
        (records(row.outputs) ?? []).map(port => [text(port.relation_alias, ''), text(port.column, '')].filter(Boolean).join('.')).filter(Boolean).join('、') || '输出端口未提供',
        row.input_semantics === 'UNKNOWN' ? '输入语义未决' : '',
        records(row.structure_inputs) ? `结构输入 ${records(row.structure_inputs)!.length} 项` : '结构输入未提供',
      ].filter(Boolean).join(' · '),
    })} />
    <Report title="分窗与排序" rows={records(result.windows)} pick={pick} describe={row => {
      const keys = records(row.keys) ?? [];
      const describeKey = (key: RecordRow) => {
        const isSort = key.clause === 'WINDOW_ORDER';
        const direction = key.descending === true ? ' DESC' : key.descending === false ? ' ASC' : ' · 方向未提供';
        return `${isSort ? '排序' : '分窗'}：${text(key.expression)}${isSort ? direction : ''}${key.binding_unknown === true ? ' · 绑定未决（输入仅为线索）' : ''}`;
      };
      return { title: [text(row.kind, '窗口'), portLabel(row.port), ...keys.map(describeKey),
        row.tie_break_verified === false ? '并列顺序未验证' : ''].filter(Boolean).join(' · '),
        evidence: [row, ...keys] };
    }} />
    <Report title="行选择" rows={records(result.row_selections)} pick={pick} describe={row => ({
      title: `${text(row.predicate, '谓词未提供')} · 读取 ${portLabel(row.producer)}`,
    })} />
    <Report title="未决项" rows={result.unknowns} describe={unknown} pick={pick} />
  </div>;
}

export function ReviewSummary({ value, pick, preview }: { value: unknown; pick: PickEvidence; preview?: PreviewEvidence }) {
  const review = record(value);
  if (!review) return <p>服务未提供结构化评审摘要。</p>;
  const paths = record(review.observed_path_demands);
  const candidates = record(review.candidate_assessment);
  const branches = records(record(review.observed_branch_demands)?.by_protected_output);
  return <div className="subfield-report-list">
    <Report title="已选根输出" rows={records(review.protected_outputs)} pick={pick}
      describe={row => ({ title: portLabel(row) })} />
    <Report title="未匹配的根输出" rows={records(review.unmatched_protected_outputs)} pick={pick}
      describe={row => ({ title: portLabel(row) })} />
    <Report title="保留与待验证项" rows={records(review.findings)} pick={pick} describe={row => ({
      title: [name(outcomes, row.decision), text(row.basis, ''), row.protected_output ? portLabel(row.protected_output) : ''].filter(Boolean).join(' · '),
      evidence: records([row.evidence, row]),
    })} />
    <Report title="已证路径需求（按根输出）" rows={records(paths?.by_protected_output)} pick={pick} describe={row => ({
      title: `${sourceLabel(row)} · ${pathLabel(row.path_tokens)} → ${portLabel(row.protected_output)}`,
      evidence: [...(records(row.port_reads) ?? []), row],
    })} />
    <Report title="过程依赖（含原始表示）" rows={records(review.observed_control_uses)?.filter(row => !isUnverifiedPhysicalRead(row))} pick={pick} describe={row => ({
      title: `${name(roleLabels, row.role)} · ${sourceLabel(row)} · ${text(row.path ?? row.expression, '范围未提供')}`,
    })} />
    <Report title="评审未决项" rows={records(review.unknowns)} describe={unknown} pick={pick} />
    {candidates && <>
      <p>示例候选键：{name(outcomes, candidates.status)} · {text(candidates.reason, '原因未提供')}</p>
      <Report title="候选键记录" rows={records(candidates.entries)} pick={pick} describe={row => ({
        title: `${text(row.key, '键未提供')} · ${name(outcomes, row.status)} · ${text(row.reason, '原因未提供')}`,
      })} />
    </>}
    {branches?.map((root, index) => {
      const observed = (records(root.by_source) ?? []).flatMap(source =>
        (records(source.paths) ?? []).flatMap(path => (records(path.reasons) ?? []).map(reason => ({
          ...reason, source: source.source, column: source.column, path_tokens: path.path_tokens,
        }))));
      return <section key={index}>
        <h3>COALESCE 分支 · {portLabel(root.protected_output)}</h3>
        <p>{observed.length ? '已列分支的值路径已追溯；' : '值路径未获确认；'}
          {root.rowset_verified === true ? '服务报告行集已验证。' : '行集未验证。'}
          {root.status === 'UNRESOLVED' ? '仍有分支未决。' : ''}</p>
        <Report title="实参值路径" rows={Array.isArray(root.by_source) ? observed : undefined} pick={pick} preview={preview} describe={row => ({
          title: `实参 ${text(row.argument_slot)} · ${sourceLabel(row)} · ${pathLabel(row.path_tokens)}`,
          evidence: [...(records(row.port_reads) ?? []), row],
        })} />
        <Report title="分支未决" rows={records(root.unresolved)} pick={pick} describe={row => ({
          title: `${row.argument_slot != null ? '实参 ' + text(row.argument_slot) : '端口'} · ${portLabel(row.port)} · ${text(row.reason)}`,
        })} />
      </section>;
    })}
  </div>;
}
