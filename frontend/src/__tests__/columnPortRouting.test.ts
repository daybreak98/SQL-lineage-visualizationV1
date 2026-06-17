import { describe, expect, it } from 'vitest';
import { buildComfortPortIndexes, getColumnPortOffsetY, layoutComfortGraph, routeComfortEdgePath } from '../graphComfortLayout';
import { getComfortNodeBox, RELATION_NODE_GEOMETRY } from '../nodeVisualTokens';
import type { GraphEdge, GraphNode } from '../types/lineage';

function relation(id: string, columnCount: number, collapsed = false): GraphNode {
  return {
    id,
    entityId: id,
    type: id.startsWith('query_result') ? 'output' : 'table',
    label: id,
    x: 0,
    y: 0,
    collapsed,
    columns: Array.from({ length: columnCount }, (_, index) => ({
      entityId: `${id}:c${index}`,
      label: `c${index}`,
      ownerEntityId: id,
      role: id.startsWith('query_result') ? 'output' : 'source',
    })),
  };
}

function pathEndY(path: string) {
  const values = path.match(/-?\d+(?:\.\d+)?/g)?.map(Number) ?? [];
  return values[values.length - 1];
}

describe('column port routing', () => {
  it('computes first, middle and last column row offsets', () => {
    const node = relation('physical_table:t', 3);
    const box = getComfortNodeBox(node);

    expect(getColumnPortOffsetY(node, 'physical_table:t:c0')).toBe(
      -box.height / 2 + RELATION_NODE_GEOMETRY.headerHeight + RELATION_NODE_GEOMETRY.bodyPaddingTop + RELATION_NODE_GEOMETRY.rowHeight / 2,
    );
    expect(getColumnPortOffsetY(node, 'physical_table:t:c1')).toBe(getColumnPortOffsetY(node, 'physical_table:t:c0')! + RELATION_NODE_GEOMETRY.rowHeight);
    expect(getColumnPortOffsetY(node, 'physical_table:t:c2')).toBe(getColumnPortOffsetY(node, 'physical_table:t:c1')! + RELATION_NODE_GEOMETRY.rowHeight);
  });

  it('falls back safely when a node is collapsed or a port is missing', () => {
    expect(getColumnPortOffsetY(relation('physical_table:t', 2, true), 'physical_table:t:c0')).toBeNull();
    expect(getColumnPortOffsetY(relation('physical_table:t', 2), 'missing')).toBeNull();
  });

  it('routes edges to column row y positions without NaN', () => {
    const source = { ...relation('physical_table:t', 2), x: 90, y: 120 };
    const target = { ...relation('query_result:final', 2), x: 320, y: 120 };
    const edge: GraphEdge = {
      id: 'e1',
      source: source.entityId,
      target: target.entityId,
      sourcePort: 'physical_table:t:c1',
      targetPort: 'query_result:final:c0',
      type: 'projection',
    };
    const ports = buildComfortPortIndexes({ nodes: [source, target], edges: [edge] });
    const path = routeComfortEdgePath({ edge, sourceNode: source, targetNode: target, ports });

    expect(path).not.toContain('NaN');
    expect(path).not.toContain('undefined');
    expect(path).toContain(`${source.x + getComfortNodeBox(source).width / 2}`);
    expect(path).toContain(`${target.x - getComfortNodeBox(target).width / 2}`);
  });

  it('keeps multiple edges to the same column port anchored on the field row', () => {
    const sourceA = { ...relation('physical_table:a', 1), x: 90, y: 80 };
    const sourceB = { ...relation('physical_table:b', 1), x: 90, y: 220 };
    const target = { ...relation('query_result:final', 2), x: 360, y: 150 };
    const targetPort = 'query_result:final:c1';
    const edges: GraphEdge[] = [
      { id: 'e1', source: sourceA.entityId, target: target.entityId, sourcePort: 'physical_table:a:c0', targetPort, type: 'projection' },
      { id: 'e2', source: sourceB.entityId, target: target.entityId, sourcePort: 'physical_table:b:c0', targetPort, type: 'projection' },
    ];
    const ports = buildComfortPortIndexes({ nodes: [sourceA, sourceB, target], edges });
    const expectedTargetY = target.y + getColumnPortOffsetY(target, targetPort)!;

    for (const edge of edges) {
      const source = edge.source === sourceA.entityId ? sourceA : sourceB;
      const path = routeComfortEdgePath({ edge, sourceNode: source, targetNode: target, ports });
      expect(pathEndY(path)).toBe(expectedTargetY);
    }
  });

  it('packs variable-height nodes in the same level without overlap', () => {
    const small = relation('physical_table:small', 2);
    const large = relation('physical_table:large', 20);
    const layouted = layoutComfortGraph({ nodes: [small, large], edges: [] }, { minNodeGap: 40 });
    const [a, b] = layouted.nodes.sort((left, right) => left.y - right.y);
    const gap = b.y - getComfortNodeBox(b).height / 2 - (a.y + getComfortNodeBox(a).height / 2);

    expect(gap).toBeGreaterThanOrEqual(40);
  });
});
