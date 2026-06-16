import { describe, expect, it } from 'vitest';
import { buildRelationColumnProjection, parsePhysicalColumnOwner } from '../relationColumnProjection';
import type { GraphEdge, GraphNode } from '../types/lineage';

function table(id: string): GraphNode {
  return { id, entityId: id, type: 'table', label: id.split('.').pop() || id, x: 0, y: 0 };
}

function column(id: string, ordinal?: number): GraphNode {
  return { id, entityId: id, type: 'column', label: id.split('.').pop() || id, x: 0, y: 0, ordinal };
}

function output(id = 'query_result:final'): GraphNode {
  return { id, entityId: id, type: 'output', label: 'Query Result', x: 0, y: 0 };
}

function outputField(id: string, label: string, ordinal?: number): GraphNode {
  return { id, entityId: id, type: 'output_field', label, x: 0, y: 0, ordinal };
}

describe('relation column projection', () => {
  it('parses physical column owner by the last dot', () => {
    expect(parsePhysicalColumnOwner('physical_column:cat.db.tbl.user_id')).toEqual({
      ownerEntityId: 'physical_table:cat.db.tbl',
      columnName: 'user_id',
    });
    expect(parsePhysicalColumnOwner('physical_column:no_column')).toBeNull();
  });

  it('groups source and output columns into relation containers with field ports', () => {
    const graph = {
      nodes: [
        table('physical_table:db.orders'),
        column('physical_column:db.orders.user_id', 2),
        column('physical_column:db.orders.order_id', 1),
        output(),
        outputField('output_column:uid', 'uid', 1),
      ],
      edges: [
        { id: 'e1', source: 'physical_column:db.orders.user_id', target: 'output_column:uid', type: 'projection', mapping: 'm1' },
        { id: 'e2', source: 'output_column:uid', target: 'query_result:final', type: 'output' },
      ] as GraphEdge[],
    };

    const projected = buildRelationColumnProjection(graph, { collapsedRelationIds: {} });
    const source = projected.nodes.find((node) => node.entityId === 'physical_table:db.orders')!;
    const result = projected.nodes.find((node) => node.entityId === 'query_result:final')!;
    const edge = projected.edges.find((item) => item.id === 'column:e1')!;

    expect(source.columns?.map((row) => row.label)).toEqual(['order_id', 'user_id']);
    expect(result.columns?.map((row) => row.entityId)).toEqual(['output_column:uid']);
    expect(edge).toMatchObject({
      source: 'physical_table:db.orders',
      sourcePort: 'physical_column:db.orders.user_id',
      target: 'query_result:final',
      targetPort: 'output_column:uid',
      originalSourceEntityId: 'physical_column:db.orders.user_id',
      originalTargetEntityId: 'output_column:uid',
      mapping: 'm1',
    });
  });

  it('creates a compatible table container when the physical table node is missing', () => {
    const projected = buildRelationColumnProjection({
      nodes: [column('physical_column:db.missing.amount'), output(), outputField('output_column:amount', 'amount')],
      edges: [
        { id: 'e1', source: 'physical_column:db.missing.amount', target: 'output_column:amount', type: 'projection' },
        { id: 'e2', source: 'output_column:amount', target: 'query_result:final', type: 'output' },
      ],
    }, { collapsedRelationIds: {} });

    expect(projected.nodes.find((node) => node.entityId === 'physical_table:db.missing')?.columns?.[0].label).toBe('amount');
  });

  it('degrades and deduplicates field edges when a relation is collapsed', () => {
    const graph = {
      nodes: [
        table('physical_table:db.orders'),
        column('physical_column:db.orders.user_id'),
        column('physical_column:db.orders.order_id'),
        output(),
        outputField('output_column:uid', 'uid'),
      ],
      edges: [
        { id: 'e1', source: 'physical_column:db.orders.user_id', target: 'output_column:uid', type: 'projection' },
        { id: 'e2', source: 'physical_column:db.orders.order_id', target: 'output_column:uid', type: 'projection' },
        { id: 'e3', source: 'output_column:uid', target: 'query_result:final', type: 'output' },
      ] as GraphEdge[],
    };

    const projected = buildRelationColumnProjection(graph, {
      collapsedRelationIds: { 'physical_table:db.orders': true },
    });

    const degraded = projected.edges.filter((edge) => edge.source === 'physical_table:db.orders' && edge.target === 'query_result:final');
    expect(degraded).toHaveLength(1);
    expect(degraded[0].sourcePort).toBeUndefined();
    expect(degraded[0].originalSourceEntityId).toBe('physical_column:db.orders.user_id');
  });

  it('keeps expression nodes as independent nodes', () => {
    const expression: GraphNode = { id: 'expression:x', entityId: 'expression:x', type: 'expression', label: 'expr', x: 0, y: 0 };
    const projected = buildRelationColumnProjection({
      nodes: [table('physical_table:t'), column('physical_column:t.a'), expression, output(), outputField('output_column:x', 'x')],
      edges: [
        { id: 'e1', source: 'physical_column:t.a', target: 'expression:x', type: 'expr' },
        { id: 'e2', source: 'expression:x', target: 'output_column:x', type: 'projection' },
        { id: 'e3', source: 'output_column:x', target: 'query_result:final', type: 'output' },
      ],
    }, { collapsedRelationIds: {} });

    expect(projected.nodes.some((node) => node.entityId === 'expression:x')).toBe(true);
    expect(projected.edges.find((edge) => edge.id === 'column:e1')).toMatchObject({ sourcePort: 'physical_column:t.a', target: 'expression:x' });
    expect(projected.edges.find((edge) => edge.id === 'column:e2')).toMatchObject({ source: 'expression:x', targetPort: 'output_column:x' });
  });
});
