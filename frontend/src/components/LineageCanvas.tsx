import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { buildPathContext, currentEntitySet, diagnosticsForEntity, viewHighlightSets } from '../data/selectors';
import { buildPortIndexes, nodeBox, routeEdgePath, visibleGraph } from '../graphPipeline';
import type { GraphEdge, GraphNode, WorkbenchState } from '../types/lineage';
import { cx } from '../utils/cx';
import { RelationNodeCard } from './LineageCanvas/RelationNodeCard';
import { buildLineageTraversalIndex, collectLineagePath } from './LineageCanvas/traversal';
import {
  applyDraggedPositions,
  clearSelectedMapping,
  selectEdgeMapping,
  selectNodeEntity,
  toggleRelationCollapsed,
} from '../workbench/actions';

interface Props {
  state: WorkbenchState;
  setState: React.Dispatch<React.SetStateAction<WorkbenchState>>;
  onNodeDoubleClick?: (entityId: string) => void;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function edgeTouchesEntity(edge: GraphEdge, entityId: string) {
  return edge.source === entityId ||
    edge.target === entityId ||
    edge.sourcePort === entityId ||
    edge.targetPort === entityId ||
    edge.originalSourceEntityId === entityId ||
    edge.originalTargetEntityId === entityId;
}

function isColumnEntitySelection(nodes: GraphNode[], entityId?: string | null) {
  if (!entityId || entityId === 'out:group') return false;
  if (entityId.startsWith('physical_column:') || entityId.startsWith('output_column:')) return true;
  return nodes.some((node) => node.columns?.some((column) => column.entityId === entityId));
}

function hasRealEntitySelection(state: WorkbenchState) {
  if (!state.selectedEntity) return false;
  return state.selectedEntity !== 'out:group' || state.detailMode !== 'collapsed';
}

function edgeEndpointEntityIds(edge: GraphEdge) {
  return [
    edge.originalSourceEntityId ?? edge.sourcePort ?? edge.source,
    edge.originalTargetEntityId ?? edge.targetPort ?? edge.target,
  ];
}

export const LINEAGE_ZOOM_BASELINE = 0.72;

export function fitZoom(bounds: { width: number; height: number } | null, viewport: { width: number; height: number }) {
  void bounds;
  void viewport;
  return LINEAGE_ZOOM_BASELINE;
}

function fitBoundsZoom(bounds: { width: number; height: number } | null, viewport: { width: number; height: number }) {
  if (!bounds || viewport.width === 0 || viewport.height === 0) return LINEAGE_ZOOM_BASELINE;
  const xFit = (viewport.width - 96) / bounds.width;
  const yFit = (viewport.height - 104) / bounds.height;
  return clamp(Math.min(xFit, yFit), 0.35, 3);
}

export function zoomDisplayPercent(zoom: number) {
  return Math.round((zoom / LINEAGE_ZOOM_BASELINE) * 100);
}

function centerOffset(
  bounds: { minX: number; minY: number; width: number; height: number } | null,
  viewport: { width: number; height: number },
  zoom: number,
) {
  if (!bounds || viewport.width === 0 || viewport.height === 0) return { x: 0, y: 0 };
  const padX = 32;
  const padY = 36;
  const scaledWidth = bounds.width * zoom;
  const scaledHeight = bounds.height * zoom;
  return {
    x: scaledWidth <= viewport.width - padX * 2
      ? (viewport.width - scaledWidth) / 2 - bounds.minX * zoom
      : padX - bounds.minX * zoom,
    y: scaledHeight <= viewport.height - padY * 2
      ? (viewport.height - scaledHeight) / 2 - bounds.minY * zoom
      : padY - bounds.minY * zoom,
  };
}

export function LineageCanvas({ state, setState, onNodeDoubleClick }: Props) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const frameRef = useRef<number | null>(null);
  const columnProjectionSelection = state.graphViewMode === 'column' ? state.selectedEntity : 'out:group';
  const columnProjectionQuery = state.graphViewMode === 'column' ? state.query : '';
  const graphInput = useMemo(() => ({
    backendGraph: state.backendGraph,
    positions: state.positions,
    graphViewMode: state.graphViewMode,
    columnContainerMode: state.columnContainerMode,
    collapsedRelationIds: state.collapsedRelationIds,
    selectedEntity: columnProjectionSelection,
    query: columnProjectionQuery,
  }), [
    state.backendGraph,
    state.positions,
    state.graphViewMode,
    state.columnContainerMode,
    state.collapsedRelationIds,
    columnProjectionSelection,
    columnProjectionQuery,
  ]);
  const graph = useMemo(() => visibleGraph(graphInput), [graphInput]);
  const current = useMemo(() => currentEntitySet(state), [state]);
  const highlights = useMemo(() => viewHighlightSets(state), [state]);
  const hasActiveSelection = hasRealEntitySelection(state);
  const ownerByEntity = useMemo(() => {
    const owners = new Map<string, string>();
    for (const node of graph.nodes) {
      owners.set(node.entityId, node.entityId);
      for (const column of node.columns ?? []) owners.set(column.entityId, node.entityId);
    }
    return owners;
  }, [graph.nodes]);
  const traversalIndex = useMemo(() => buildLineageTraversalIndex(graph.edges), [graph.edges]);
  const upstreamPath = useMemo(
    () => hasActiveSelection
      ? collectLineagePath(traversalIndex, state.selectedEntity, 'upstream')
      : { entityIds: new Set<string>(), edgeIds: new Set<string>() },
    [hasActiveSelection, state.selectedEntity, traversalIndex],
  );
  const downstreamPath = useMemo(
    () => hasActiveSelection
      ? collectLineagePath(traversalIndex, state.selectedEntity, 'downstream')
      : { entityIds: new Set<string>(), edgeIds: new Set<string>() },
    [hasActiveSelection, state.selectedEntity, traversalIndex],
  );
  const selectedEdges = upstreamPath.edgeIds;
  const downstreamImpact = useMemo(() => {
    const nodeIds = new Set<string>();
    for (const entityId of downstreamPath.entityIds) {
      nodeIds.add(ownerByEntity.get(entityId) ?? entityId);
    }
    return { nodeIds, edgeIds: downstreamPath.edgeIds };
  }, [downstreamPath, ownerByEntity]);
  const selectedNodeIds = useMemo(() => {
    const entityId = state.selectedEntity;
    if (!hasActiveSelection) return new Set<string>();
    const ids = new Set<string>([entityId, ownerByEntity.get(entityId) ?? entityId]);
    for (const source of upstreamPath.entityIds) {
      ids.add(source);
      ids.add(ownerByEntity.get(source) ?? source);
    }
    return ids;
  }, [hasActiveSelection, ownerByEntity, state.selectedEntity, upstreamPath.entityIds]);
  const columnPathEntityIds = useMemo(() => {
    if (!isColumnEntitySelection(graph.nodes, state.selectedEntity)) return current;
    const ids = new Set<string>();
    if (state.selectedEntity) ids.add(state.selectedEntity);
    for (const edge of graph.edges) {
      if (!selectedEdges.has(edge.id) && !downstreamImpact.edgeIds.has(edge.id)) continue;
      const [source, target] = edgeEndpointEntityIds(edge);
      ids.add(source);
      ids.add(target);
    }
    return ids;
  }, [current, downstreamImpact.edgeIds, graph.edges, graph.nodes, selectedEdges, state.selectedEntity]);
  const upstreamColumnEntityIds = useMemo(() => {
    if (!isColumnEntitySelection(graph.nodes, state.selectedEntity)) return new Set<string>();
    const ids = new Set<string>();
    for (const edge of graph.edges) {
      if (!selectedEdges.has(edge.id)) continue;
      const [source, target] = edgeEndpointEntityIds(edge);
      ids.add(source);
      ids.add(target);
    }
    if (state.selectedEntity) ids.delete(state.selectedEntity);
    return ids;
  }, [graph.edges, graph.nodes, selectedEdges, state.selectedEntity]);
  const downstreamColumnEntityIds = useMemo(() => {
    if (!isColumnEntitySelection(graph.nodes, state.selectedEntity)) return new Set<string>();
    const ids = new Set<string>();
    for (const edge of graph.edges) {
      if (!downstreamImpact.edgeIds.has(edge.id)) continue;
      const [source, target] = edgeEndpointEntityIds(edge);
      ids.add(source);
      ids.add(target);
    }
    if (state.selectedEntity) ids.delete(state.selectedEntity);
    return ids;
  }, [downstreamImpact.edgeIds, graph.edges, graph.nodes, state.selectedEntity]);
  const columnSelectionActive = isColumnEntitySelection(graph.nodes, state.selectedEntity);
  const [drag, setDrag] = useState<{ id: string; ox: number; oy: number } | null>(null);
  const [panDrag, setPanDrag] = useState<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const [draftPositions, setDraftPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [manualPan, setManualPan] = useState({ x: 0, y: 0 });
  const [zoomOverride, setZoomOverride] = useState<number | null>(null);
  const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 });
  const dragRef = useRef(drag);
  const panDragRef = useRef(panDrag);
  const draftPositionsRef = useRef(draftPositions);
  const pendingPointerRef = useRef<{ x: number; y: number } | null>(null);
  const pathContext = buildPathContext(state);
  const graphViewMode = state.graphViewMode ?? 'table';
  const upstreamNodeIds = useMemo(() => {
    if (!hasActiveSelection || graphViewMode !== 'table') return new Set<string>();
    return upstreamPath.entityIds;
  }, [graphViewMode, hasActiveSelection, upstreamPath.entityIds]);
  const upstreamEdgeIds = graphViewMode === 'table' && hasActiveSelection
    ? upstreamPath.edgeIds
    : new Set<string>();
  const byEntity = useMemo(
    () => Object.fromEntries(graph.nodes.map((node) => [node.entityId, node])),
    [graph.nodes],
  );
  const positions = useMemo(
    () => ({ ...Object.fromEntries(graph.nodes.map((node) => [node.id, { x: node.x, y: node.y }])), ...state.positions, ...draftPositions }),
    [graph.nodes, state.positions, draftPositions],
  );
  const graphBounds = useMemo(() => {
    if (!graph.nodes.length) return null;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const node of graph.nodes) {
      const box = nodeBox(node);
      minX = Math.min(minX, node.x - box.width / 2);
      minY = Math.min(minY, node.y - box.height / 2);
      maxX = Math.max(maxX, node.x + box.width / 2);
      maxY = Math.max(maxY, node.y + box.height / 2);
    }
    return { minX, minY, width: maxX - minX, height: maxY - minY };
  }, [graph.nodes]);
  const defaultZoom = useMemo(() => fitZoom(graphBounds, viewportSize), [graphBounds, viewportSize]);
  const zoom = zoomOverride ?? defaultZoom;
  const zoomStep = LINEAGE_ZOOM_BASELINE * 0.25;
  const autoOffset = useMemo(() => centerOffset(graphBounds, viewportSize, zoom), [graphBounds, viewportSize, zoom]);
  const viewOffset = useMemo(() => ({ x: autoOffset.x + manualPan.x, y: autoOffset.y + manualPan.y }), [autoOffset, manualPan]);

  dragRef.current = drag;
  panDragRef.current = panDrag;
  draftPositionsRef.current = draftPositions;

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const updateSize = () => setViewportSize({ width: viewport.clientWidth, height: viewport.clientHeight });
    updateSize();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(updateSize);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setManualPan({ x: 0, y: 0 });
    setZoomOverride(null);
    setDraftPositions({});
  }, [state.backendGraph, state.graphViewMode]);

  useEffect(() => {
    if (!state.canvasCommand) return;
    if (state.canvasCommand.type === 'fit') {
      const nextZoom = fitBoundsZoom(graphBounds, viewportSize);
      setZoomOverride(nextZoom);
      setManualPan({ x: 0, y: 0 });
      setDraftPositions({});
      return;
    }
    if (state.canvasCommand.type === 'center') {
      setManualPan({ x: 0, y: 0 });
      setDraftPositions({});
      return;
    }
    if (state.canvasCommand.type === 'reset') {
      setZoomOverride(null);
      setManualPan({ x: 0, y: 0 });
      setDraftPositions({});
    }
  }, [state.canvasCommand, graphBounds, viewportSize]);

  useEffect(() => {
    if (!drag && !panDrag) return;
    document.body.style.userSelect = 'none';

    const finishInteraction = () => {
      if (frameRef.current != null) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
      if (pendingPointerRef.current) applyPointer(pendingPointerRef.current.x, pendingPointerRef.current.y);
      pendingPointerRef.current = null;
      const activeDrag = dragRef.current;
      if (activeDrag && Object.keys(draftPositionsRef.current).length > 0) {
        const nextPositions = draftPositionsRef.current;
        setState((s) => applyDraggedPositions(s, nextPositions));
      }
      setDraftPositions({});
      setDrag(null);
      setPanDrag(null);
      document.body.style.userSelect = '';
    };

    const handleMove = (event: MouseEvent) => queuePointer(event.clientX, event.clientY);
    const handleUp = () => finishInteraction();
    const handleBlur = () => finishInteraction();

    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    window.addEventListener('blur', handleBlur);
    return () => {
      if (frameRef.current != null) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
      pendingPointerRef.current = null;
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
      window.removeEventListener('blur', handleBlur);
    };
  }, [drag, panDrag, setState, viewOffset.x, viewOffset.y, zoom]);

  const startDrag = (event: React.MouseEvent, node: GraphNode) => {
    event.stopPropagation();
    event.preventDefault();
    const rect = viewportRef.current?.getBoundingClientRect();
    if (!rect) return;
    const position = positions[node.id] ?? { x: node.x, y: node.y };
    setDrag({
      id: node.id,
      ox: (event.clientX - rect.left - viewOffset.x) / zoom - position.x,
      oy: (event.clientY - rect.top - viewOffset.y) / zoom - position.y,
    });
  };

  const startPan = (event: React.MouseEvent) => {
    if (event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest('.node, .relation-node, .edge, .edge-hit, button, .stats, .mode-tip, .path-anchor')) return;
    event.preventDefault();
    setPanDrag({ x: event.clientX, y: event.clientY, panX: manualPan.x, panY: manualPan.y });
    setState((s) => clearSelectedMapping(s));
  };

  const zoomBy = (nextZoom: number, anchor?: { clientX: number; clientY: number }) => {
    const rect = viewportRef.current?.getBoundingClientRect();
    const newZoom = clamp(nextZoom, 0.25, 3);
    if (!rect || !graphBounds) {
      setZoomOverride(newZoom);
      return;
    }
    const clientX = anchor?.clientX ?? rect.left + rect.width / 2;
    const clientY = anchor?.clientY ?? rect.top + rect.height / 2;
    const contentX = (clientX - rect.left - viewOffset.x) / zoom;
    const contentY = (clientY - rect.top - viewOffset.y) / zoom;
    const nextAuto = centerOffset(graphBounds, viewportSize, newZoom);
    setZoomOverride(newZoom);
    setManualPan({
      x: clientX - rect.left - nextAuto.x - contentX * newZoom,
      y: clientY - rect.top - nextAuto.y - contentY * newZoom,
    });
  };

  const handleWheel = (event: React.WheelEvent) => {
    event.preventDefault();
    const factor = event.deltaY > 0 ? 0.9 : 1.1;
    zoomBy(zoom * factor, { clientX: event.clientX, clientY: event.clientY });
  };

  const applyPointer = (clientX: number, clientY: number) => {
    const activePan = panDragRef.current;
    if (activePan) {
      setManualPan({
        x: activePan.panX + clientX - activePan.x,
        y: activePan.panY + clientY - activePan.y,
      });
      return;
    }

    const activeDrag = dragRef.current;
    if (!activeDrag) return;
    const rect = viewportRef.current?.getBoundingClientRect();
    if (!rect) return;
    setDraftPositions((prev) => ({
      ...prev,
      [activeDrag.id]: {
        x: (clientX - rect.left - viewOffset.x) / zoom - activeDrag.ox,
        y: (clientY - rect.top - viewOffset.y) / zoom - activeDrag.oy,
      },
    }));
  };

  const queuePointer = (clientX: number, clientY: number) => {
    pendingPointerRef.current = { x: clientX, y: clientY };
    if (frameRef.current != null) return;
    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = null;
      const point = pendingPointerRef.current;
      if (!point) return;
      applyPointer(point.x, point.y);
    });
  };

  return (
    <div
      ref={viewportRef}
      className={cx('viewport', panDrag && 'panning')}
      onMouseDown={startPan}
      onMouseMove={(event) => applyPointer(event.clientX, event.clientY)}
      onWheel={handleWheel}
      style={{ position: 'relative' }}
    >
      <div style={{ position: 'absolute', top: 4, right: 4, zIndex: 50, display: 'flex', gap: 4 }}>
        <button className="btn h-[24px] px-2 text-[11px]" onClick={() => zoomBy(zoom - zoomStep)}>-</button>
        <span className="pill" style={{ minWidth: 48, textAlign: 'center' }}>{zoomDisplayPercent(zoom)}%</span>
        <button className="btn h-[24px] px-2 text-[11px]" onClick={() => zoomBy(zoom + zoomStep)}>+</button>
        <button className="btn h-[24px] px-2 text-[11px]" onClick={() => { setZoomOverride(null); setManualPan({ x: 0, y: 0 }); }}>Reset</button>
      </div>
      {!(state.pageMode === 'analyzed' && state.trustStatus === 'trusted') && <div className="message block">{state.pageMode === 'failed' ? 'Analysis failed | Search disabled | fix SQL and re-analyze.' : state.pageMode === 'empty' ? 'Paste SQL or load example.' : 'Analyze SQL to build subquery dependency view.'}</div>}
      <div className={cx('mode-tip', ['subquery_dependency', 'large_graph', 'full_graph_preview', 'focus_field'].includes(state.renderMode) && 'show')}>
        {state.renderMode === 'subquery_dependency' ? 'Default Subquery Dependency View | field entities preserved, hidden by default' : state.renderMode === 'full_graph_preview' ? 'Full Graph Preview | user-triggered only' : state.renderMode === 'focus_field' ? 'Focus Field Mode | local field expansion' : 'Large Graph Mode | render degradation, not failed'}
      </div>
      <div className={cx('path-anchor', state.renderMode !== 'subquery_dependency' && state.detailMode !== 'expanded' && 'show')}>
        <div className="path-anchor-title"><span className={cx('dot', pathContext.status === 'stale' && 'stale', ['partial', 'low_confidence'].includes(pathContext.status) && 'warn')} /><span>{state.selectedOutput ? `${pathContext.display} | ${pathContext.status}` : 'Choose output'}</span></div>
        <div className="path-anchor-body">{state.selectedOutput ? `PathContextStore | ${pathContext.nodes} nodes | ${pathContext.mappings} mappings | ${pathContext.warnings} warnings` : 'Default view shows subquery / CTE dependency.'}</div>
      </div>
      <div className="canvas-transform" style={{ transform: `translate(${viewOffset.x}px, ${viewOffset.y}px)`, transformOrigin: 'top left' }}>
        <div className="stage" style={{ transform: `scale(${zoom})`, transformOrigin: 'top left' }} onClick={() => setState((s) => clearSelectedMapping(s))}>
          <svg className="edge-layer">
            <defs>
              <marker id="arrowDefault" markerWidth="6.3" markerHeight="6.3" refX="5.6" refY="2.1" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,4.2 L5.6,2.1 z" fill="#94A3B8" /></marker>
              <marker id="arrowPrimary" markerWidth="6.3" markerHeight="6.3" refX="5.6" refY="2.1" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,4.2 L5.6,2.1 z" fill="#2563EB" /></marker>
              <marker id="arrowDownstream" markerWidth="6.3" markerHeight="6.3" refX="5.6" refY="2.1" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,4.2 L5.6,2.1 z" fill="#F59E0B" /></marker>
            </defs>
            {(() => {
              const ports = buildPortIndexes(graph, positions);

              return graph.edges.map((edge: GraphEdge) => {
                const sourceNode = byEntity[edge.source];
                const targetNode = byEntity[edge.target];
                if (!sourceNode || !targetNode) return null;
                const sourcePos = positions[sourceNode.id] ?? { x: sourceNode.x, y: sourceNode.y };
                const targetPos = positions[targetNode.id] ?? { x: targetNode.x, y: targetNode.y };
                const edgePath = routeEdgePath({ edge, sourceNode, targetNode, sourcePos, targetPos, ports, style: 'smooth' });
                const isCurrent = (current.has(edge.source) && current.has(edge.target)) || state.selectedMapping === edge.mapping;
                const isSelectedEdge = selectedEdges.has(edge.id);
                const isUpstreamEdge = upstreamEdgeIds.has(edge.id);
                const isDownstreamImpactEdge = downstreamImpact.edgeIds.has(edge.id);
                const isRelated = isSelectedEdge || isUpstreamEdge || isDownstreamImpactEdge || edgeTouchesEntity(edge, state.selectedEntity) || (!columnSelectionActive && selectedNodeIds.has(edge.source) && selectedNodeIds.has(edge.target));
                const dimmed = hasActiveSelection && !isRelated;
                const isViewHighlighted = highlights.highlightedEdgeIds.has(edge.id);
                const markerEnd = isDownstreamImpactEdge
                  ? 'url(#arrowDownstream)'
                  : (isCurrent || isSelectedEdge || isUpstreamEdge)
                    ? 'url(#arrowPrimary)'
                    : 'url(#arrowDefault)';
                return (
                  <g key={edge.id} onClick={(event) => event.stopPropagation()} onDoubleClick={(event) => {
                    event.stopPropagation();
                    const targetEntity = edge.originalTargetEntityId ?? edge.targetPort ?? edge.target;
                    setState((s) => selectEdgeMapping(s, targetEntity, edge.mapping || null));
                  }}>
                    <path className="edge-hit" d={edgePath} />
                    <path className={cx('edge', edge.type, isCurrent && 'current', dimmed && 'dimmed', isViewHighlighted && 'view-highlight', (isSelectedEdge || isUpstreamEdge) && 'edge-selected', isDownstreamImpactEdge && 'downstream-impact', edge.synthetic && state.graphViewMode !== 'table' && 'synthetic')} d={edgePath} markerEnd={markerEnd} />
                  </g>
                );
              });
            })()}
          </svg>
          {graph.nodes.map((node) => {
            const position = positions[node.id] ?? { x: node.x, y: node.y };
            const box = nodeBox(node);
            const selected = state.selectedEntity === node.entityId || Boolean(node.columns?.some((column) => column.entityId === state.selectedEntity));
            const relationSelected = state.selectedEntity === node.entityId;
            const isCurrent = current.has(node.entityId) || Boolean(node.columns?.some((column) => current.has(column.entityId)));
            const inSelection = hasActiveSelection && selectedNodeIds.has(node.entityId);
            const isUpstreamNode = upstreamNodeIds.has(node.entityId);
            const isDownstreamImpactNode = downstreamImpact.nodeIds.has(node.entityId);
            const dimmed = hasActiveSelection && !selected && !inSelection && !isUpstreamNode && !isDownstreamImpactNode;
            const warning = diagnosticsForEntity(state, node.entityId).length > 0 || node.type === 'unknown';
            const isViewHighlighted = highlights.highlightedEntityIds.has(node.entityId);
            if (node.columns) {
              return (
                <div key={node.id} style={{ position: 'absolute', left: position.x - box.width / 2, top: position.y - box.height / 2 }}>
                  <RelationNodeCard
                    node={node}
                    box={box}
                    selectedEntityId={state.selectedEntity}
                    currentEntityIds={current}
                    activeColumnEntityIds={columnPathEntityIds}
                    upstreamColumnEntityIds={upstreamColumnEntityIds}
                    downstreamColumnEntityIds={downstreamColumnEntityIds}
                    dimmed={dimmed}
                    warning={warning}
                    dragging={drag?.id === node.id}
                    downstreamImpact={columnSelectionActive ? false : isDownstreamImpactNode}
                    stale={state.trustStatus === 'stale'}
                    viewHighlighted={isViewHighlighted}
                    onSelectRelation={(entityId) => setState((s) => selectNodeEntity(s, entityId))}
                    onSelectColumn={(entityId) => setState((s) => selectNodeEntity(s, entityId))}
                    onDoubleClickEntity={(entityId) => {
                      setState((s) => selectNodeEntity(s, entityId));
                      if (state.selectedEntity !== entityId) onNodeDoubleClick?.(entityId);
                    }}
                    onToggleCollapsed={(entityId) => setState((s) => toggleRelationCollapsed(s, entityId))}
                    onStartDrag={startDrag}
                  />
                </div>
              );
            }
            return (
              <div key={node.id} className="node" style={{ left: position.x - box.width / 2, top: position.y - box.height / 2 }} data-type={node.type} data-full-label={node.label} data-selected={relationSelected || undefined} data-current={isCurrent || undefined} data-upstream={isUpstreamNode || undefined} data-downstream-impact={isDownstreamImpactNode || undefined} data-warning={warning || undefined} data-stale={state.trustStatus === 'stale' || undefined} data-dimmed={dimmed || undefined} data-dragging={drag?.id === node.id || undefined} data-view-highlight={isViewHighlighted || undefined} onMouseDown={(event) => startDrag(event, node)} onDoubleClick={(event) => { event.stopPropagation(); setState((s) => selectNodeEntity(s, node.entityId)); if (state.selectedEntity !== node.entityId) onNodeDoubleClick?.(node.entityId); }}>
                <span className="title">{node.label}</span><span className="state-dot" />
              </div>
            );
          })}
        </div>
      </div>
      <div className="stats"><h4>GraphRenderMode</h4><div className="stats-grid"><span>mode</span><b>{state.renderMode.replace('_dependency', '').replace('current_field_', 'field_')}</b><span>view</span><b>{graphViewMode}</b><span>visible</span><b>{graph.nodes.length}/{graph.edges.length}</b><span>layout</span><b>{state.lastTransition?.includes('layout:recompute') ? 'recomputed' : 'stable'}</b><span>labels</span><b>{drag ? 'off' : 'lazy'}</b></div></div>
    </div>
  );
}
