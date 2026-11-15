import type { GraphEdge } from '../../types/lineage';

interface TraversalLink {
  entityId: string;
  edgeId: string;
}

export interface LineageTraversalIndex {
  incoming: Map<string, TraversalLink[]>;
  outgoing: Map<string, TraversalLink[]>;
}

export interface LineagePath {
  entityIds: Set<string>;
  edgeIds: Set<string>;
}

function edgeEndpointEntityIds(edge: GraphEdge): [string, string] {
  return [
    edge.originalSourceEntityId ?? edge.sourcePort ?? edge.source,
    edge.originalTargetEntityId ?? edge.targetPort ?? edge.target,
  ];
}

export function buildLineageTraversalIndex(edges: GraphEdge[]): LineageTraversalIndex {
  const incoming = new Map<string, TraversalLink[]>();
  const outgoing = new Map<string, TraversalLink[]>();

  for (const edge of edges) {
    const [source, target] = edgeEndpointEntityIds(edge);
    const incomingLinks = incoming.get(target) ?? [];
    incomingLinks.push({ entityId: source, edgeId: edge.id });
    incoming.set(target, incomingLinks);

    const outgoingLinks = outgoing.get(source) ?? [];
    outgoingLinks.push({ entityId: target, edgeId: edge.id });
    outgoing.set(source, outgoingLinks);
  }

  return { incoming, outgoing };
}

export function collectLineagePath(
  index: LineageTraversalIndex,
  startEntityId: string,
  direction: 'upstream' | 'downstream',
): LineagePath {
  const linksByEntity = direction === 'upstream' ? index.incoming : index.outgoing;
  const entityIds = new Set<string>();
  const edgeIds = new Set<string>();
  const visited = new Set<string>([startEntityId]);
  const queue = [startEntityId];

  for (let cursor = 0; cursor < queue.length; cursor += 1) {
    const entityId = queue[cursor];
    for (const link of linksByEntity.get(entityId) ?? []) {
      edgeIds.add(link.edgeId);
      if (visited.has(link.entityId)) continue;
      visited.add(link.entityId);
      entityIds.add(link.entityId);
      queue.push(link.entityId);
    }
  }

  return { entityIds, edgeIds };
}
