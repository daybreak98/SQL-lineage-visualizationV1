import { memo, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { Graph, RecordRow } from './contract';

const MIN_ZOOM = .75;
const initialZoom = (available: number, graphWidth: number) => Math.max(MIN_ZOOM, Math.min(1, available / graphWidth));
const roleNames = { relation: '源关系', column: '源列', path: 'JSON 路径', root: '根输出', slot: '投影端口', unknown: '未决记录' };

export const ReactGraph = memo(function ReactGraph({ graph, emptyMessage, onPick }: {
  graph: Graph | null; emptyMessage: string; onPick: (name: string, rows: RecordRow[]) => void;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [active, setActive] = useState('');
  const layout = useMemo(() => {
    const totals: number[] = [];
    const positions = new Map(graph?.nodes.map(node => {
      const row = totals[node.lane] ?? 0;
      totals[node.lane] = row + 1;
      return [node.key, { x: node.lane * 202 + 18, y: row * 78 + 48, label: node.label }];
    }));
    return { positions, width: Math.max(1, totals.length) * 202 + 12,
      height: Math.max(245, 65 + totals.reduce((max, count) => Math.max(max, count), 0) * 78) };
  }, [graph]);
  useLayoutEffect(() => {
    if (graph?.nodes.length && viewport.current) {
      setZoom(initialZoom(viewport.current.clientWidth, layout.width));
    }
  }, [graph, layout.width]);
  function pick(id: string, title: string, rows: Set<RecordRow>) {
    setActive(id);
    onPick(title, [...rows]);
  }
  return <>
    <div className="canvas-tools tool-zoom">
      <button type="button" aria-label="缩小" disabled={!graph?.nodes.length || zoom <= MIN_ZOOM} onClick={() => setZoom(v => Math.max(MIN_ZOOM, v - .15))}>−</button>
      <output>{Math.round(zoom * 100)}%</output>
      <button type="button" aria-label="放大" disabled={!graph?.nodes.length} onClick={() => setZoom(v => Math.min(1.8, v + .15))}>＋</button>
      <button type="button" disabled={!graph?.nodes.length} title="适应窗口，查看全图；可再放大阅读" onClick={() => {
        const canvas = viewport.current;
        if (!canvas?.clientWidth || !canvas.clientHeight) return;
        setZoom(Math.min(1, canvas.clientWidth / layout.width, canvas.clientHeight / layout.height));
        canvas.scrollTo(0, 0);
      }}>适配</button>
    </div>
    <div ref={viewport} id="lineage-canvas" tabIndex={0} aria-label="血缘画布，可滚动查看">
      {!graph?.nodes.length ? <p className="canvas-note muted">{graph ? '没有可绘制的确认端口，请查看证据或未决记录。' : emptyMessage}</p> :
      <div className="canvas-world canvas-world-compact" style={{ width: layout.width, height: layout.height, zoom }}>
        {(graph.lanes ?? ['源关系', 'JSON 路径', '投影端口', '未决记录']).map((label, lane) =>
          <span className="canvas-lane" key={label} style={{ left: lane * 202 + 18 }}>{label}</span>)}
        <svg width={layout.width} height={layout.height} className="canvas-edges">
          {graph.edges.map((edge, index) => {
            const from = layout.positions.get(edge.from), to = layout.positions.get(edge.to);
            if (!from || !to) return null;
            const id = 'edge-' + index, title = `${from.label} → ${to.label}`;
            const start = from.x + 176, mid = (start + to.x) / 2;
            const d = `M${start},${from.y + 31} C${mid},${from.y + 31} ${mid},${to.y + 31} ${to.x},${to.y + 31}`;
            const activate = () => pick(id, title, edge.evidence);
            return <g key={id}>
              <path data-edge="" className="canvas-edge-hit" d={d}
                tabIndex={0} role="button" aria-label={title} aria-pressed={id === active}
                onClick={activate} onKeyDown={event => {
                  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); }
                }} />
              <path className={edge.uncertain ? 'canvas-edge-line uncertain' : 'canvas-edge-line'} d={d} aria-hidden="true" />
            </g>;
          })}
        </svg>
        {graph.nodes.map(node => {
          const pos = layout.positions.get(node.key)!;
          const role = node.kind ?? (node.lane === 0 ? 'relation' : node.lane === 1 ? 'column' : node.root ? 'root' : 'slot');
          return <button key={node.key} type="button" className={`canvas-node${node.uncertain ? ' uncertain' : ''}`}
            data-role={role} title={node.label} aria-pressed={node.key === active}
            style={{ left: pos.x, top: pos.y, width: 176, height: 62 }}
            onClick={() => pick(node.key, node.label, node.evidence)}>
            <span className="canvas-role">{node.uncertain && role !== 'unknown' ? '未决 · ' : ''}{roleNames[role]}</span>
            <span className="canvas-caption">{node.display ?? node.label}</span>
          </button>;
        })}
      </div>}
    </div>
  </>;
});
