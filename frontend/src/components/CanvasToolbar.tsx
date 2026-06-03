import type React from 'react';
import { buildPathContext } from '../data/selectors';
import type { GraphViewMode, WorkbenchState } from '../types/lineage';
import { cx } from '../utils/cx';

interface Props {
  state: WorkbenchState;
  setState: React.Dispatch<React.SetStateAction<WorkbenchState>>;
  onTransition: (event: string) => void;
}

const VIEW_MODES: { mode: GraphViewMode; label: string; title: string }[] = [
  { mode: 'subquery', label: 'Subquery', title: 'Subquery/CTE structure view: tables -> subqueries -> Query Result' },
  { mode: 'table', label: 'Table', title: 'Table-level view: physical tables + Query Result' },
  { mode: 'column', label: 'Column', title: 'Column-level view: expanded field nodes' },
  { mode: 'expression', label: 'Expr', title: 'Expression view: highlight expression nodes and edges' },
  { mode: 'semantics', label: 'Semantics', title: 'Semantics view: Filter/Join/Aggregate annotations' },
  { mode: 'diagnostics', label: 'Diag', title: 'Diagnostics view: highlight diagnostic nodes' },
];

export function CanvasToolbar({ state, setState, onTransition }: Props) {
  const pc = buildPathContext(state);
  return (
    <div className="toolbar">
      <div className="tool-left">
        <span className="tool-title">Canvas</span>
        <button className="tool-btn">Fit Path</button>
        <button className="tool-btn">Center</button>
        <button className="tool-btn" onClick={() => setState((s) => ({ ...s, positions: {} }))}>Reset Viewport</button>
        <button className="tool-btn" onClick={() => onTransition('CLEAR_SELECTION')}>Clear</button>
        <button className="tool-btn" onClick={() => state.selectedOutput && onTransition('FOCUS_FIELD')}>Focus</button>
        <button className="tool-btn" onClick={() => setState((s) => ({ ...s, drawerOpen: true, drawerTab: 'taxonomy' }))}>?</button>
        <div className="path-inline">
          <span className={cx('dot', pc.status === 'stale' && 'stale', ['partial', 'low_confidence'].includes(pc.status) && 'warn')} />
          <span id="pathText">{state.selectedOutput ? `${pc.display} · ${pc.status} · ${pc.nodes} nodes · ${pc.mappings} mappings` : 'Subquery dependency view · choose output for field path'}</span>
          <span className="badge">{state.renderMode}</span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <div className="view-toggle">
          {VIEW_MODES.map(({ mode, label, title }) => (
            <button
              key={mode}
              className={cx('view-btn', state.graphViewMode === mode && 'active')}
              title={title}
              onClick={() => setState((s) => ({ ...s, graphViewMode: mode, positions: {} }))}
            >
              {label}
            </button>
          ))}
        </div>
        <button className="tool-btn" onClick={() => onTransition('OPEN_FULL_PREVIEW')}>Full Preview</button>
        <button className="tool-btn" onClick={() => setState((s) => ({ ...s, detailMode: s.detailMode === 'collapsed' ? 'compact' : 'collapsed' }))}>{state.detailMode === 'collapsed' ? 'Show Detail' : 'Hide Detail'}</button>
      </div>
    </div>
  );
}
