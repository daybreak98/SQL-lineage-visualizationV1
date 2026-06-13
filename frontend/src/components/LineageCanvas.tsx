import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { buildPathContext, currentEntitySet, diagnosticsForEntity, viewHighlightSets } from '../data/selectors';
import { buildPortIndexes, nodeBox, routeEdgePath, visibleGraph } from '../graphPipeline';
import type { GraphEdge, GraphNode, WorkbenchState } from '../types/lineage';
import { cx } from '../utils/cx';
import {
  applyDraggedPositions,
  clearSelectedMapping,
  selectEdgeMapping,
  selectNodeEntity,
} from '../workbench/actions';

interface Props {
  state: WorkbenchState;
  setState: React.Dispatch<React.SetStateAction<WorkbenchState>>;
  onNodeDoubleClick?: (entityId: string) => void;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export function fitZoom(bounds: { width: number; height: number } | null, viewport: { width: number; height: number }) {
  if (!bounds || viewport.width === 0 || viewport.height === 0) return 1;
  const xFit = (viewport.width - 96) / bounds.width;
  const yFit = (viewport.height - 104) / bounds.height;
  return clamp(Math.min(1, xFit, yFit), 0.35, 1);
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
  const graph = useMemo(() => visibleGraph(state), [state]);
  const current = useMemo(() => currentEntitySet(state), [state]);
  const highlights = useMemo(() => viewHighlightSets(state), [state]);
  const selectedEdges = useMemo(() => {
    const entityId = state.selectedEntity;
    if (!entityId || entityId === 'out:group') return new Set<string>();
    const ids = new Set<string>();
    const reverse = new Map<string, string[]>();
    const edgeByKey = new Map<string, string>();
    graph.edges.forEach((edge) => {
      if (!reverse.has(edge.target)) reverse.set(edge.target, []);
      reverse.get(edge.target)!.push(edge.source);
      edgeByKey.set(`${edge.source}->${edge.target}`, edge.id);
    });
    const visited = new Set<string>([entityId]);
    const queue = [entityId];
    while (queue.length > 0) {
      const currentEntity = queue.shift()!;
      for (const source of reverse.get(currentEntity) ?? []) {
        const key = `${source}->${currentEntity}`;
        const edgeId = edgeByKey.get(key);
        if (edgeId) ids.add(edgeId);
        if (!visited.has(source)) {
          visited.add(source);
          queue.push(source);
        }
      }
    }
    return ids;
  }, [state.selectedEntity, graph.edges]);
  const selectedNodeIds = useMemo(() => {
    const entityId = state.selectedEntity;
    if (!entityId || entityId === 'out:group') return new Set<string>();
    const ids = new Set<string>([entityId]);
    const reverse = new Map<string, string[]>();
    graph.edges.forEach((edge) => {
      if (!reverse.has(edge.target)) reverse.set(edge.target, []);
      reverse.get(edge.target)!.push(edge.source);
    });
    const queue = [entityId];
    while (queue.length > 0) {
      const currentEntity = queue.shift()!;
      for (const source of reverse.get(currentEntity) ?? []) {
        if (!ids.has(source)) {
          ids.add(source);
          queue.push(source);
        }
      }
    }
    return ids;
  }, [state.selectedEntity, graph.edges]);
  const hasActiveSelection = state.selectedEntity && state.selectedEntity !== 'out:group';
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
  const byEntity = Object.fromEntries(graph.nodes.map((node) => [node.entityId, node]));
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
      const box = nodeBox(node.type);
      minX = Math.min(minX, node.x - box.width / 2);
      minY = Math.min(minY, node.y - box.height / 2);
      maxX = Math.max(maxX, node.x + box.width / 2);
      maxY = Math.max(maxY, node.y + box.height / 2);
    }
    return { minX, minY, width: maxX - minX, height: maxY - minY };
  }, [graph.nodes]);
  const defaultZoom = useMemo(() => fitZoom(graphBounds, viewportSize), [graphBounds, viewportSize]);
  const zoom = zoomOverride ?? defaultZoom;
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
    if (target.closest('.node, .edge, .edge-hit, button, .stats, .mode-tip, .path-anchor')) return;
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
        <button className="btn h-[24px] px-2 text-[11px]" onClick={() => zoomBy(zoom - 0.25)}>-</button>
        <span className="pill" style={{ minWidth: 48, textAlign: 'center' }}>{Math.round(zoom * 100)}%</span>
        <button className="btn h-[24px] px-2 text-[11px]" onClick={() => zoomBy(zoom + 0.25)}>+</button>
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
                const isRelated = isSelectedEdge || (selectedNodeIds.has(edge.source) && selectedNodeIds.has(edge.target));
                const dimmed = hasActiveSelection && !isRelated;
                const isViewHighlighted = highlights.highlightedEdgeIds.has(edge.id);
                const markerEnd = (isCurrent || isSelectedEdge) ? 'url(#arrowPrimary)' : 'url(#arrowDefault)';
                return (
                  <g key={edge.id} onClick={(event) => event.stopPropagation()} onDoubleClick={(event) => { event.stopPropagation(); setState((s) => selectEdgeMapping(s, edge.target, edge.mapping || null)); }}>
                    <path className="edge-hit" d={edgePath} />
                    <path className={cx('edge', edge.type, isCurrent && 'current', dimmed && 'dimmed', isViewHighlighted && 'view-highlight', isSelectedEdge && 'edge-selected', edge.synthetic && 'synthetic')} d={edgePath} markerEnd={markerEnd} />
                  </g>
                );
              });
            })()}
          </svg>
          {graph.nodes.map((node) => {
            const position = positions[node.id] ?? { x: node.x, y: node.y };
            const box = nodeBox(node.type);
            const selected = state.selectedEntity === node.entityId;
            const isCurrent = current.has(node.entityId);
            const inSelection = hasActiveSelection && selectedNodeIds.has(node.entityId);
            const dimmed = hasActiveSelection && !selected && !inSelection;
            const warning = diagnosticsForEntity(state, node.entityId).length > 0 || node.type === 'unknown';
            const isViewHighlighted = highlights.highlightedEntityIds.has(node.entityId);
            return (
              <div key={node.id} className="node" style={{ left: position.x - box.width / 2, top: position.y - box.height / 2 }} data-type={node.type} data-selected={selected || undefined} data-current={isCurrent || undefined} data-warning={warning || undefined} data-stale={state.trustStatus === 'stale' || undefined} data-dimmed={dimmed || undefined} data-dragging={drag?.id === node.id || undefined} data-view-highlight={isViewHighlighted || undefined} onMouseDown={(event) => startDrag(event, node)} onDoubleClick={(event) => { event.stopPropagation(); setState((s) => selectNodeEntity(s, node.entityId)); if (state.selectedEntity !== node.entityId) onNodeDoubleClick?.(node.entityId); }}>
                <span className="strip" /><span className="title" title={node.label}>{node.label}</span><span className="state-dot" />
              </div>
            );
          })}
        </div>
      </div>
      <div className="stats"><h4>GraphRenderMode</h4><div className="stats-grid"><span>mode</span><b>{state.renderMode.replace('_dependency', '').replace('current_field_', 'field_')}</b><span>view</span><b>{graphViewMode}</b><span>visible</span><b>{graph.nodes.length}/{graph.edges.length}</b><span>layout</span><b>{state.lastTransition?.includes('layout:recompute') ? 'recomputed' : 'stable'}</b><span>labels</span><b>{drag ? 'off' : 'lazy'}</b></div></div>
    </div>
  );
}
