from __future__ import annotations

from app.domain.graph_view_model import GraphEdge, GraphModel, GraphNode
from app.services.predicate_dependency_service import PredicateDependency


def build_predicate_dependency_graph(
    predicates: list[PredicateDependency],
) -> GraphModel:
    graph = GraphModel(view_mode="expression")
    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}

    for predicate in predicates:
        owner_type, owner_label = _predicate_owner(predicate.owner_id)
        nodes.setdefault(
            predicate.owner_id,
            GraphNode(
                id=predicate.owner_id,
                node_type=owner_type,
                label=owner_label,
            ),
        )
        nodes.setdefault(
            predicate.predicate_id,
            GraphNode(
                id=predicate.predicate_id,
                node_type="expression",
                label=_predicate_label(predicate),
            ),
        )

        dependency_type, effect_type = _predicate_edge_types(
            predicate.predicate_kind
        )
        for root in predicate.root_columns:
            source_id = f"physical_column:{root.display()}"
            nodes.setdefault(
                source_id,
                GraphNode(
                    id=source_id,
                    node_type="physical_column",
                    label=root.display(),
                ),
            )
            edge = GraphEdge(
                id=f"edge:{source_id}->{predicate.predicate_id}:{dependency_type}",
                source=source_id,
                target=predicate.predicate_id,
                edge_type=dependency_type,
            )
            edges.setdefault(edge.id, edge)

        effect_edge = GraphEdge(
            id=f"edge:{predicate.predicate_id}->{predicate.owner_id}:{effect_type}",
            source=predicate.predicate_id,
            target=predicate.owner_id,
            edge_type=effect_type,
        )
        edges.setdefault(effect_edge.id, effect_edge)

    graph.nodes = list(nodes.values())
    graph.edges = list(edges.values())
    return graph


def _predicate_edge_types(predicate_kind: str) -> tuple[str, str]:
    prefixes = {
        "join": "join",
        "group_by": "group",
        "order_by": "order",
        "distribute_by": "distribute",
        "sort_by": "sort",
        "cluster_by": "cluster",
    }
    prefix = prefixes.get(predicate_kind, "predicate")
    return f"{prefix}_dependency", f"{prefix}_effect"


def _predicate_label(predicate: PredicateDependency) -> str:
    normalized = " ".join(predicate.expression.split())
    limit = 180
    if len(normalized) > limit:
        normalized = f"{normalized[:limit - 3]}..."
    kind_label = predicate.predicate_kind.upper().replace("_", " ")
    return f"{kind_label}: {normalized}"


def _predicate_owner(owner_id: str) -> tuple[str, str]:
    if owner_id.startswith("cte:"):
        return "cte", owner_id.split(":", 1)[1]
    if owner_id.startswith("subquery:"):
        return "subquery", owner_id.split(":", 1)[1]
    return "output", "Query Result"
