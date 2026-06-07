import { describe, expect, it } from 'vitest';
import { buildComfortPortIndexes, layoutComfortGraph } from '../graphComfortLayout';
import type { GraphEdge, GraphNode } from '../types/lineage';

function node(id: string, rank: number, orderInRank: number): GraphNode {
  return {
    id,
    entityId: id,
    type: id.startsWith('out') ? 'output_field' : 'table',
    label: id,
    x: 0,
    y: 0,
    rank,
    orderInRank,
  };
}

describe('graph layout hints', () => {
  it('uses backend rank and order when laying out nodes', () => {
    const graph = {
      nodes: [
        node('src:a', 0, 0),
        node('src:b', 0, 1),
        node('out:later', 4, 1),
        node('out:first', 4, 0),
      ],
      edges: [
        { id: 'e1', source: 'src:a', target: 'out:later', type: 'projection' },
        { id: 'e2', source: 'src:b', target: 'out:first', type: 'projection' },
      ] as GraphEdge[],
    };

    const layouted = layoutComfortGraph(graph, {
      minWidth: 800,
      minHeight: 400,
      marginX: 40,
      marginY: 40,
      minRankGap: 120,
      minNodeGap: 60,
    });
    const byId = new Map(layouted.nodes.map((n) => [n.entityId, n]));

    expect(byId.get('out:first')!.x).toBeGreaterThan(byId.get('src:a')!.x);
    expect(byId.get('out:first')!.y).toBeLessThan(byId.get('out:later')!.y);
  });

  it('uses backend source and target port order before y-position sorting', () => {
    const graph = {
      nodes: [
        { ...node('src', 0, 0), y: 100 },
        { ...node('out:a', 1, 0), y: 200 },
        { ...node('out:b', 1, 1), y: 80 },
      ],
      edges: [
        { id: 'edge-b', source: 'src', target: 'out:b', type: 'projection', sourcePortOrder: 1 },
        { id: 'edge-a', source: 'src', target: 'out:a', type: 'projection', sourcePortOrder: 0 },
      ] as GraphEdge[],
    };

    const ports = buildComfortPortIndexes(graph);

    expect(ports.sourcePortIndex.get('edge-a')).toBe(0);
    expect(ports.sourcePortIndex.get('edge-b')).toBe(1);
  });
});
