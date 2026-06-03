import type React from 'react';
import { entityName } from '../data/selectors';
import type { WorkbenchState } from '../types/lineage';
import { cx } from '../utils/cx';

interface Props {
  state: WorkbenchState;
  setState: React.Dispatch<React.SetStateAction<WorkbenchState>>;
}

function statusClass(state: WorkbenchState) {
  if (state.pageMode === 'failed') return 'failed';
  if (state.pageMode === 'analyzing') return 'running';
  if (state.analysisStatus === 'partial') return 'partial';
  if (state.trustStatus === 'trusted') return 'trusted';
  if (state.trustStatus === 'stale') return 'stale';
  return '';
}

export function StatusStrip({ state, setState }: Props) {
  return (
    <div className="status">
      <div className="status-left">
        <span className={cx('pill', statusClass(state))}>{state.pageMode}</span>
        <span>{state.analysisStatus}</span>
        <span>{state.trustStatus}</span>
        <span>render: {state.renderMode}</span>
        <span>view: {state.graphViewMode}</span>
        <span className="truncate">output: <b>{state.selectedOutput ? entityName(state.selectedOutput) : 'none'}</b></span>
        <span className="truncate">selected: <b>{entityName(state.selectedEntity)}</b></span>
      </div>
      <button className="btn h-6 text-[11px]" onClick={() => setState((s) => ({ ...s, drawerOpen: !s.drawerOpen }))}>More</button>
    </div>
  );
}
