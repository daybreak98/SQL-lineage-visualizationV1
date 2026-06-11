import type React from 'react';
import { milestones, snapshots } from '../data/mockLineage';
import type { Diagnostic, WorkbenchState } from '../types/lineage';
import { cx } from '../utils/cx';
import {
  openFullPreview,
  resetWorkspaceLayout,
  setDrawerTab,
} from '../workbench/actions';

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
    body = <div className="cards">{state.backendMessage && <div className="card"><div className="card-title">Backend status</div>{state.backendMessage}</div>}{activeDiagnostics.length ? activeDiagnostics.map((diagnostic) => <DiagnosticCard key={diagnostic.id} diagnostic={diagnostic} />) : <div className="card"><div className="card-title">Diagnostics</div>No backend diagnostics for the latest analysis.</div>}</div>;
  } else if (state.drawerTab === 'render') {
    const rows = [
      ['ANY', 'ANALYZE_SUCCESS', 'subquery_dependency', 'reset / recompute'],
      ['subquery_dependency', 'SELECT_OUTPUT_FIELD', 'current_field_path', 'reset / no'],
      ['current_field_path', 'FOCUS_FIELD', 'focus_field', 'preserve / no'],
      ['current_field_path', 'OPEN_SEMANTIC_MODE', 'semantic_mode', 'preserve / no'],
      ['ANY', 'ENTER_LARGE_GRAPH', 'large_graph', 'preserve / no'],
      ['ANY', 'OPEN_FULL_PREVIEW', 'full_graph_preview', 'reset / optional'],
      ['current/focus/semantic', 'CLEAR_SELECTION', 'subquery_dependency', 'reset / no'],
    ];
    body = <><div className="card mb-2"><div className="card-title">Last transition</div>{state.lastTransition || 'initial | subquery_dependency'}</div>{rows.map((row) => <div key={row.join('-')} className="row4"><b>{row[0]}</b><span>{row[1]}</span><span>{row[2]}</span><span>{row[3]}</span></div>)}</>;
  } else if (state.drawerTab === 'taxonomy') {
    const rows = [
      ['Output', 'solid blue border / light blue fill / OUT', 'final focus node'],
      ['Subquery', 'purple dashed frame / dual border / SUBQ', 'default structure-view core node'],
      ['CTE', 'sky solid border / light cyan fill / CTE', 'stable logic block'],
      ['Table', 'slate thin border / restrained visual', 'context source node'],
      ['Expression', 'purple thin border / EXPR', 'derived logic node'],
      ['Unknown', 'orange dashed border / warning', 'confidence risk'],
    ];
    body = rows.map((row) => <div key={row[0]} className="row4"><b>{row[0]}</b><span>{row[1]}</span><span>{row[2]}</span><span>state-safe</span></div>);
  } else if (state.drawerTab === 'snapshots') {
    body = snapshots.map((snapshot) => <div key={snapshot[0]} className="snapshot"><span><b>{snapshot[0]}</b> | {snapshot[1]}</span><button className="btn h-6 text-[11px]">checkpoint</button></div>);
  } else if (state.drawerTab === 'milestones') {
    body = <div className="cards">{milestones.map((milestone) => <div key={milestone[0]} className="card"><div className="card-title">{milestone[0]} | {milestone[1]}</div>{milestone[2]}</div>)}</div>;
  } else {
    body = (
      <div className="cards">
        <div className="card">
          <div className="card-title">Reset split ratio</div>
          <button className="btn" onClick={() => setState((s) => ({ ...s, split: 44 }))}>Reset to 44/56</button>
        </div>
        <div className="card">
          <div className="card-title">Reset workspace layout</div>
          <button className="btn" onClick={() => setState((s) => resetWorkspaceLayout(s))}>Reset workspace</button>
        </div>
        <div className="card">
          <div className="card-title">Open Full Preview</div>
          <button className="btn" onClick={() => setState((s) => openFullPreview(s))}>Full Graph Preview</button>
        </div>
      </div>
    );
  }

  const tabs = ['diagnostics', 'render', 'taxonomy', 'snapshots', 'milestones', 'more'];

  return (
    <div className={cx('drawer', state.drawerOpen && 'open')}>
      <div className="drawer-tabs">
        {tabs.map((tab) => <button key={tab} className={cx('drawer-tab', state.drawerTab === tab && 'active')} onClick={() => setState((s) => setDrawerTab(s, tab))}>{tab === 'taxonomy' ? 'Node Taxonomy' : tab === 'milestones' ? 'M1-M7' : tab}</button>)}
      </div>
      <div className="drawer-body">{body}</div>
    </div>
  );
}
