import type { DetailTab, GraphViewMode, WorkbenchState } from '../types/lineage';
import { transitionRenderMode } from '../data/selectors';

let canvasCommandId = 0;

export function issueCanvasCommand(state: WorkbenchState, type: 'fit' | 'center' | 'reset'): WorkbenchState {
  return { ...state, canvasCommand: { type, id: ++canvasCommandId } };
}

export function resetViewport(state: WorkbenchState): WorkbenchState {
  return issueCanvasCommand({ ...state, positions: {} }, 'reset');
}

export function openDrawer(state: WorkbenchState, drawerTab: string): WorkbenchState {
  return { ...state, drawerOpen: true, drawerTab };
}

export function setDrawerTab(state: WorkbenchState, drawerTab: string): WorkbenchState {
  return { ...state, drawerTab };
}

export function switchGraphViewMode(state: WorkbenchState, graphViewMode: GraphViewMode): WorkbenchState {
  return { ...state, graphViewMode, positions: {} };
}

export function toggleDetailCollapsed(state: WorkbenchState): WorkbenchState {
  return { ...state, detailMode: state.detailMode === 'collapsed' ? 'compact' : 'collapsed' };
}

export function expandDetailToMapping(state: WorkbenchState): WorkbenchState {
  return { ...state, detailMode: 'expanded', detailTab: 'mapping' };
}

export function toggleDetailExpanded(state: WorkbenchState): WorkbenchState {
  return { ...state, detailMode: state.detailMode === 'expanded' ? 'compact' : 'expanded' };
}

export function collapseDetail(state: WorkbenchState): WorkbenchState {
  return { ...state, detailMode: 'collapsed' };
}

export function setDetailTab(state: WorkbenchState, detailTab: DetailTab): WorkbenchState {
  return { ...state, detailTab };
}

export function focusSelectedOutputPath(state: WorkbenchState): WorkbenchState {
  if (!state.selectedOutput) return state;
  return { ...state, renderMode: 'current_field_path' };
}

export function clearSelectedMapping(state: WorkbenchState): WorkbenchState {
  if (!state.selectedMapping) return state;
  return { ...state, selectedMapping: null };
}

export function resetWorkspaceLayout(state: WorkbenchState): WorkbenchState {
  return {
    ...state,
    split: 44,
    selectedOutput: null,
    selectedEntity: 'out:group',
    selectedMapping: null,
    renderMode: 'subquery_dependency',
  };
}

export function openFullPreview(state: WorkbenchState): WorkbenchState {
  return { ...state, renderMode: 'full_graph_preview' };
}

export function applyDraggedPositions(
  state: WorkbenchState,
  positions: Record<string, { x: number; y: number }>,
): WorkbenchState {
  if (Object.keys(positions).length === 0) return state;
  return {
    ...state,
    positions: {
      ...state.positions,
      ...positions,
    },
  };
}

export function selectEdgeMapping(
  state: WorkbenchState,
  targetEntity: string,
  mapping: string | null,
): WorkbenchState {
  const alreadySelected = state.selectedEntity === targetEntity && state.selectedMapping === mapping;
  return {
    ...state,
    selectedMapping: alreadySelected ? null : mapping,
    selectedEntity: alreadySelected ? 'out:group' : targetEntity,
    detailMode: 'compact',
    detailTab: alreadySelected ? 'summary' : (mapping ? 'mapping' : 'summary'),
  };
}

export function selectNodeEntity(state: WorkbenchState, entityId: string): WorkbenchState {
  const alreadySelected = state.selectedEntity === entityId && !(entityId === 'out:group' && state.detailMode === 'collapsed');
  return {
    ...state,
    selectedEntity: alreadySelected ? 'out:group' : entityId,
    selectedMapping: null,
    detailMode: alreadySelected ? 'collapsed' : 'compact',
    detailTab: 'summary',
  };
}

export function clearSelection(state: WorkbenchState): WorkbenchState {
  const transition = transitionRenderMode(state.renderMode, 'CLEAR_SELECTION');
  return {
    ...state,
    selectedOutput: null,
    selectedEntity: 'out:group',
    selectedMapping: null,
    detailMode: 'collapsed',
    detailTab: 'summary',
    renderMode: transition.mode,
    lastTransition: transition.description,
  };
}

export function toggleRelationCollapsed(state: WorkbenchState, entityId: string): WorkbenchState {
  const collapsedRelationIds = { ...state.collapsedRelationIds };
  if (collapsedRelationIds[entityId]) {
    delete collapsedRelationIds[entityId];
  } else {
    collapsedRelationIds[entityId] = true;
  }

  return {
    ...state,
    collapsedRelationIds,
    lastTransition: `${state.graphViewMode} -> ${state.graphViewMode} | viewport:preserve | layout:recompute | reason:collapse-change`,
  };
}
