import { describe, expect, it } from 'vitest';

import type { GraphEdge } from '../../../types/lineage';
import { buildLineageTraversalIndex, collectLineagePath } from '../traversal';

const edges: GraphEdge[] = [
  {
    id: 'edge:source->middle',
    source: 'relation:source',
    target: 'relation:middle',
    sourcePort: 'physical_column:source.amount',
    targetPort: 'column:middle.amount',
    type: 'projection',
  },
  {
    id: 'edge:middle->output',
    source: 'relation:middle',
    target: 'relation:output',
    originalSourceEntityId: 'column:middle.amount',
    originalTargetEntityId: 'output_column:amount',
    type: 'projection',
  },
];

describe('lineage traversal index', () => {
  it('traces upstream and downstream through column-level edge endpoints', () => {
    const index = buildLineageTraversalIndex(edges);

    const upstream = collectLineagePath(index, 'output_column:amount', 'upstream');
    expect(upstream.entityIds).toEqual(new Set([
      'column:middle.amount',
      'physical_column:source.amount',
    ]));
    expect(upstream.edgeIds).toEqual(new Set([
      'edge:middle->output',
      'edge:source->middle',
    ]));

    const downstream = collectLineagePath(index, 'physical_column:source.amount', 'downstream');
    expect(downstream.entityIds).toEqual(new Set([
      'column:middle.amount',
      'output_column:amount',
    ]));
    expect(downstream.edgeIds).toEqual(new Set([
      'edge:source->middle',
      'edge:middle->output',
    ]));
  });

  it('terminates safely when the graph contains a cycle', () => {
    const cyclic = buildLineageTraversalIndex([
      ...edges,
      {
        id: 'edge:output->source',
        source: 'output_column:amount',
        target: 'physical_column:source.amount',
        type: 'projection',
      },
    ]);

    const path = collectLineagePath(cyclic, 'output_column:amount', 'downstream');
    expect(path.entityIds.has('output_column:amount')).toBe(false);
    expect(path.edgeIds.size).toBe(3);
  });
});
