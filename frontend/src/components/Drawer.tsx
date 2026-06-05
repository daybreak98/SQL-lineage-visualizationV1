import type React from 'react';
import { milestones, snapshots } from '../data/mockLineage';
import type { Diagnostic, WorkbenchState } from '../types/lineage';
import { cx } from '../utils/cx';

interface Props {
  state: WorkbenchState;
  setState: React.Dispatch<React.SetStateAction<WorkbenchState>>;
}

function DiagnosticCard({ diagnostic }: { diagnostic: Diagnostic }) {
  return <div className={cx('card diag', diagnostic.severity)}><div className="card-title">{diagnostic.code}</div><b>Reason:</b> {diagnostic.reason}<br /><b>Impact:</b> {diagnostic.impact}<br /><b>Action:</b> {diagnostic.action}</div>;
}

export function Drawer({ state, setState }: Props) {
  let body: React.ReactNode;
  if (state.drawerTab === 'diagnostics') {
    const activeDiagnostics = state.backendDiagnostics ?? [];
    body = <div className="cards">{state.backendMessage && <div className="card"><div className="card-title">Backend status</div>{state.backendMessage}</div>}{activeDiagnostics.length ? activeDiagnostics.map((d) => <DiagnosticCard key={d.id} diagnostic={d} />) : <div className="card"><div className="card-title">Diagnostics</div>No backend diagnostics for the latest analysis.</div>}</div>;
  }
  else if (state.drawerTab === 'render') {
    const rows = [
      ['ANY', 'ANALYZE_SUCCESS', 'subquery_dependency', 'reset / recompute'],
      ['subquery_dependency', 'SELECT_OUTPUT_FIELD', 'current_field_path', 'reset / no'],
      ['current_field_path', 'FOCUS_FIELD', 'focus_field', 'preserve / no'],
      ['current_field_path', 'OPEN_SEMANTIC_MODE', 'semantic_mode', 'preserve / no'],
      ['ANY', 'ENTER_LARGE_GRAPH', 'large_graph', 'preserve / no'],
      ['ANY', 'OPEN_FULL_PREVIEW', 'full_graph_preview', 'reset / optional'],
      ['current/focus/semantic', 'CLEAR_SELECTION', 'subquery_dependency', 'reset / no'],
    ];
    body = <><div className="card mb-2"><div className="card-title">Last transition</div>{state.lastTransition || 'initial · subquery_dependency'}</div>{rows.map((r) => <div key={r.join('-')} className="row4"><b>{r[0]}</b><span>{r[1]}</span><span>{r[2]}</span><span>{r[3]}</span></div>)}</>;
  } else if (state.drawerTab === 'taxonomy') {
    const rows = [
      ['Output', '主蓝 2px 实线 / 浅蓝背景 / OUT', '最终关注点'],
      ['Subquery', '紫色虚线 + 双层边框 / SUBQ', '默认结构视图核心节点'],
      ['CTE', '天蓝实线 / 浅青背景 / CTE', '稳定逻辑块'],
      ['Table', '灰蓝细边，克制，无默认 TBL badge', '上下文，不抢主视觉'],
      ['Expression', '紫色细边 / EXPR', '辅助派生逻辑'],
      ['Unknown', '橙色虚线 / ? / warning', '可信度风险'],
    ];
    body = rows.map((r) => <div key={r[0]} className="row4"><b>{r[0]}</b><span>{r[1]}</span><span>{r[2]}</span><span>state-safe</span></div>);
  } else if (state.drawerTab === 'snapshots') {
    body = snapshots.map((s) => <div key={s[0]} className="snapshot"><span><b>{s[0]}</b> · {s[1]}</span><button className="btn h-6 text-[11px]">checkpoint</button></div>);
  } else if (state.drawerTab === 'milestones') {
    body = <div className="cards">{milestones.map((m) => <div key={m[0]} className="card"><div className="card-title">{m[0]} · {m[1]}</div>{m[2]}</div>)}</div>;
  } else {
    body = <div className="cards"><div className="card"><div className="card-title">Reset split ratio</div><button className="btn" onClick={() => setState((s) => ({ ...s, split: 44 }))}>Reset to 44/56</button></div><div className="card"><div className="card-title">Reset workspace layout</div><button className="btn" onClick={() => setState((s) => ({ ...s, split: 44, selectedOutput: null, selectedEntity: 'out:group', selectedMapping: null, renderMode: 'subquery_dependency' }))}>Reset workspace</button></div><div className="card"><div className="card-title">Open Full Preview</div><button className="btn" onClick={() => setState((s) => ({ ...s, renderMode: 'full_graph_preview' }))}>Full Graph Preview</button></div></div>;
  }

  const tabs = ['diagnostics', 'render', 'taxonomy', 'snapshots', 'milestones', 'more'];
  return (
    <div className={cx('drawer', state.drawerOpen && 'open')}>
      <div className="drawer-tabs">
        {tabs.map((tab) => <button key={tab} className={cx('drawer-tab', state.drawerTab === tab && 'active')} onClick={() => setState((s) => ({ ...s, drawerTab: tab }))}>{tab === 'taxonomy' ? 'Node Taxonomy' : tab === 'milestones' ? 'M1-M7' : tab}</button>)}
      </div>
      <div className="drawer-body">{body}</div>
    </div>
  );
}
