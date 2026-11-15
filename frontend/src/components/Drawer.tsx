import type React from 'react';
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

  if (state.drawerTab === 'more') {
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
  } else {
    const activeDiagnostics = state.backendDiagnostics ?? [];
    body = <div className="cards">{state.backendMessage && <div className="card"><div className="card-title">Backend status</div>{state.backendMessage}</div>}{activeDiagnostics.length ? activeDiagnostics.map((diagnostic) => <DiagnosticCard key={diagnostic.id} diagnostic={diagnostic} />) : <div className="card"><div className="card-title">Diagnostics</div>No backend diagnostics for the latest analysis.</div>}</div>;
  }

  const tabs = ['diagnostics', 'more'];

  return (
    <div className={cx('drawer', state.drawerOpen && 'open')}>
      <div className="drawer-tabs">
        {tabs.map((tab) => <button key={tab} className={cx('drawer-tab', state.drawerTab === tab && 'active')} onClick={() => setState((s) => setDrawerTab(s, tab))}>{tab}</button>)}
      </div>
      <div className="drawer-body">{body}</div>
    </div>
  );
}
