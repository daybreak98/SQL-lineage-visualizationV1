import type { GraphEdge, GraphNode } from './types/lineage';
import { COMFORT_CANVAS, getComfortNodeBox } from './nodeVisualTokens';

export type ComfortGraph = { nodes: GraphNode[]; edges: GraphEdge[] };
export type ManualPositions = Record<string, { x: number; y: number }>;

// ============================================================
// 手动位置应用：layout 之后执行
// ============================================================

export function applyManualPositions(graph: ComfortGraph, positions: ManualPositions): ComfortGraph {
  return {
    nodes: graph.nodes.map((node) => {
      const saved = positions[node.id] || positions[node.entityId];
      if (!saved) return node;
      return { ...node, x: saved.x, y: saved.y, pinned: true };
    }),
    edges: graph.edges,
  };
}

// ============================================================
// 邻接表构建
// ============================================================

function buildAdjacency(nodes: GraphNode[], edges: GraphEdge[]) {
  const ids = new Set(nodes.map((n) => n.entityId));
  const incoming = new Map<string, string[]>();
  const outgoing = new Map<string, string[]>();

  nodes.forEach((n) => {
    incoming.set(n.entityId, []);
    outgoing.set(n.entityId, []);
  });

  edges.forEach((e) => {
    if (!ids.has(e.source) || !ids.has(e.target)) return;
    incoming.get(e.target)?.push(e.source);
    outgoing.get(e.source)?.push(e.target);
  });

  return { incoming, outgoing };
}

function nodeTypeRankSeed(node: GraphNode) {
  if (node.type === 'table' || node.type === 'column') return 0;
  if (node.type === 'cte') return 1;
  if (node.type === 'subquery' || node.type === 'expression') return 2;
  if (node.type === 'output' || node.type === 'output_field') return 99;
  return 1;
}

// ============================================================
// 最长路径层级计算（DFS + memo）
// ============================================================

function computeLongestPathLevels(nodes: GraphNode[], edges: GraphEdge[]) {
  const { incoming } = buildAdjacency(nodes, edges);
  const nodeById = new Map(nodes.map((n) => [n.entityId, n]));
  const levels = new Map<string, number>();

  const visit = (id: string, stack = new Set<string>()): number => {
    if (levels.has(id)) return levels.get(id)!;
    if (stack.has(id)) return 0;

    const node = nodeById.get(id);
    if (!node) return 0;
    if (node.type === 'output' || node.type === 'output_field') return 0;

    stack.add(id);
    const parents = incoming.get(id) || [];
    const level = parents.length
      ? Math.max(...parents.map((p) => visit(p, stack))) + 1
      : nodeTypeRankSeed(node);
    stack.delete(id);

    levels.set(id, level);
    return level;
  };

  nodes.forEach((n) => {
    if (n.type !== 'output' && n.type !== 'output_field') visit(n.entityId);
  });

  const maxNonOutputLevel = Math.max(
    0,
    ...nodes
      .filter((n) => n.type !== 'output' && n.type !== 'output_field')
      .map((n) => levels.get(n.entityId) ?? nodeTypeRankSeed(n)),
  );

  nodes.forEach((n) => {
    if (n.type === 'output' || n.type === 'output_field') levels.set(n.entityId, maxNonOutputLevel + 1);
  });

  return levels;
}

function groupByLevel(nodes: GraphNode[], levels: Map<string, number>) {
  const groups = new Map<number, GraphNode[]>();
  nodes.forEach((n) => {
    const level = levels.get(n.entityId) ?? 0;
    if (!groups.has(level)) groups.set(level, []);
    groups.get(level)!.push(n);
  });
  return groups;
}

// ============================================================
// barycenter 同层排序
// ============================================================

function orderWithinLevelsByBarycenter(
  nodes: GraphNode[],
  edges: GraphEdge[],
  levels: Map<string, number>,
) {
  const groups = groupByLevel(nodes, levels);
  const { incoming, outgoing } = buildAdjacency(nodes, edges);
  const maxLevel = Math.max(0, ...Array.from(groups.keys()));

  function indexMapForLevel(level: number) {
    const map = new Map<string, number>();
    (groups.get(level) || []).forEach((n, i) => map.set(n.entityId, i));
    return map;
  }

  function barycenter(neighborIds: string[], neighborIndex: Map<string, number>) {
    const values = neighborIds.map((id) => neighborIndex.get(id)).filter((v): v is number => v !== undefined);
    if (!values.length) return Number.POSITIVE_INFINITY;
    return values.reduce((s, v) => s + v, 0) / values.length;
  }

  for (let pass = 0; pass < 4; pass++) {
    for (let level = 1; level <= maxLevel; level++) {
      const prev = indexMapForLevel(level - 1);
      (groups.get(level) || []).sort(
        (a, b) => barycenter(incoming.get(a.entityId) || [], prev) - barycenter(incoming.get(b.entityId) || [], prev),
      );
    }
    for (let level = maxLevel - 1; level >= 0; level--) {
      const next = indexMapForLevel(level + 1);
      (groups.get(level) || []).sort(
        (a, b) => barycenter(outgoing.get(a.entityId) || [], next) - barycenter(outgoing.get(b.entityId) || [], next),
      );
    }
  }

  return groups;
}

function resolveCollisionsByLevel(groups: Map<number, GraphNode[]>, minGap: number) {
  for (const list of groups.values()) {
    list.sort((a, b) => a.y - b.y);
    for (let i = 1; i < list.length; i++) {
      if (list[i].y - list[i - 1].y < minGap) list[i].y = list[i - 1].y + minGap;
    }
  }
}

// ============================================================
// ★ 舒适布局主入口
// ============================================================

export function layoutComfortGraph(graph: ComfortGraph, options?: {
  minWidth?: number;
  minHeight?: number;
  marginX?: number;
  marginY?: number;
  minRankGap?: number;
  minNodeGap?: number;
}): ComfortGraph & { width: number; height: number } {
  const cfg = { ...COMFORT_CANVAS, ...options };
  const nodes = graph.nodes.map((n) => ({ ...n }));
  const { edges } = graph;

  if (!nodes.length) return { nodes, edges, width: cfg.minWidth, height: cfg.minHeight };

  const levels = computeLongestPathLevels(nodes, edges);
  const groups = orderWithinLevelsByBarycenter(nodes, edges, levels);
  const maxLevel = Math.max(1, ...Array.from(groups.keys()));
  const maxGroupSize = Math.max(1, ...Array.from(groups.values()).map((l) => l.length));

  const width = Math.max(cfg.minWidth, cfg.marginX * 2 + maxLevel * cfg.minRankGap + 220);
  const height = Math.max(cfg.minHeight, cfg.marginY * 2 + maxGroupSize * cfg.minNodeGap);
  const rankGap = Math.max(cfg.minRankGap, (width - cfg.marginX * 2) / Math.max(maxLevel, 1));

  for (const [level, list] of groups.entries()) {
    const availableHeight = height - cfg.marginY * 2;
    const yGap = availableHeight / (list.length + 1);

    list.forEach((node, index) => {
      node.x = Math.min(width - cfg.marginX, cfg.marginX + level * rankGap);
      node.y = Math.min(height - cfg.marginY, Math.max(cfg.marginY, cfg.marginY + yGap * (index + 1)));
      (node as any).level = level;
    });
  }

  const { incoming, outgoing } = buildAdjacency(nodes, edges);
  nodes.forEach((n) => {
    (n as any).indegree = incoming.get(n.entityId)?.length || 0;
    (n as any).outdegree = outgoing.get(n.entityId)?.length || 0;
  });

  resolveCollisionsByLevel(groups, cfg.minNodeGap);

  return { nodes, edges, width, height };
}

// ============================================================
// ★ 舒适边路由：沿中心连线方向 + 柔和曲线
// ============================================================

function portOffset(index: number, count: number, gap = 8) {
  if (count <= 1) return 0;
  return (index - (count - 1) / 2) * gap;
}

export function buildComfortPortIndexes(graph: ComfortGraph) {
  const nodeById = new Map(graph.nodes.map((n) => [n.entityId, n]));
  const outgoing = new Map<string, GraphEdge[]>();
  const incoming = new Map<string, GraphEdge[]>();

  for (const edge of graph.edges) {
    if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) continue;
    if (!outgoing.has(edge.source)) outgoing.set(edge.source, []);
    if (!incoming.has(edge.target)) incoming.set(edge.target, []);
    outgoing.get(edge.source)!.push(edge);
    incoming.get(edge.target)!.push(edge);
  }

  for (const list of outgoing.values()) {
    list.sort((a, b) => (nodeById.get(a.target)?.y ?? 0) - (nodeById.get(b.target)?.y ?? 0));
    list.forEach((_, i) => {});  // no-op, just keeping the template
  }
  for (const list of incoming.values()) {
    list.sort((a, b) => (nodeById.get(a.source)?.y ?? 0) - (nodeById.get(b.source)?.y ?? 0));
  }

  const sourcePortIndex = new Map<string, number>();
  const sourcePortCount = new Map<string, number>();
  const targetPortIndex = new Map<string, number>();
  const targetPortCount = new Map<string, number>();

  for (const [source, list] of outgoing.entries()) {
    sourcePortCount.set(source, list.length);
    list.forEach((edge, i) => sourcePortIndex.set(edge.id, i));
  }
  for (const [target, list] of incoming.entries()) {
    targetPortCount.set(target, list.length);
    list.forEach((edge, i) => targetPortIndex.set(edge.id, i));
  }

  return { sourcePortIndex, sourcePortCount, targetPortIndex, targetPortCount };
}

export function routeComfortEdgePath(params: {
  edge: GraphEdge;
  sourceNode: GraphNode;
  targetNode: GraphNode;
  ports?: ReturnType<typeof buildComfortPortIndexes>;
}) {
  const { edge, sourceNode, targetNode, ports } = params;
  const sourceBox = getComfortNodeBox(sourceNode.type);
  const targetBox = getComfortNodeBox(targetNode.type);

  const dx = targetNode.x - sourceNode.x;
  const dy = targetNode.y - sourceNode.y;
  const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);

  const sourceCount = ports?.sourcePortCount.get(edge.source) ?? 1;
  const sourceIndex = ports?.sourcePortIndex.get(edge.id) ?? 0;
  const targetCount = ports?.targetPortCount.get(edge.target) ?? 1;
  const targetIndex = ports?.targetPortIndex.get(edge.id) ?? 0;

  const sx = sourceNode.x + (dx / dist) * (sourceBox.width * 0.42);
  const sy = sourceNode.y + (dy / dist) * (sourceBox.height * 0.42) + portOffset(sourceIndex, sourceCount, 7);
  const tx = targetNode.x - (dx / dist) * (targetBox.width * 0.46);
  const ty = targetNode.y - (dy / dist) * (targetBox.height * 0.46) + portOffset(targetIndex, targetCount, 7);

  const mx = (sx + tx) / 2;
  const absDx = Math.abs(tx - sx);

  if (absDx < 80) {
    const loop = 96;
    return `M ${sx} ${sy} C ${sx + loop} ${sy}, ${tx + loop} ${ty}, ${tx} ${ty}`;
  }

  return `M ${sx} ${sy} C ${mx} ${sy}, ${mx} ${ty}, ${tx} ${ty}`;
}
