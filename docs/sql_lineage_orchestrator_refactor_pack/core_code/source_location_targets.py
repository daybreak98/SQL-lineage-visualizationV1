"""
Reference implementation: source_location_targets.py

Goal:
- Build SourceLocation target entities from graph nodes.
- Ensure SourceLocation entityId matches graph node entityId/id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal


SourceEntityType = Literal["output_column", "physical_table", "cte"]
MatchRole = Literal["select_output", "table_reference", "cte_definition"]


@dataclass(frozen=True)
class SourceLocationTarget:
    entity_id: str
    entity_type: SourceEntityType
    name: str
    match_role: MatchRole


def extract_source_location_targets_from_graph(graph: Any) -> list[SourceLocationTarget]:
    """Extract location targets from GraphModel / GraphViewModel.

    Expected node shape examples:
        GraphNode(id="physical_table:dwd_order_di", node_type="physical_table", label="dwd_order_di")
        {"id": "cte:order_base", "node_type": "cte", "label": "order_base"}

    Adjust `_node_get` if your GraphNode fields differ.
    """
    nodes = _graph_nodes(graph)
    targets: list[SourceLocationTarget] = []
    seen: set[str] = set()

    for node in nodes:
        node_type = _node_get(node, "node_type") or _node_get(node, "type")
        entity_id = _node_get(node, "entity_id") or _node_get(node, "entityId") or _node_get(node, "id")
        label = _node_get(node, "label") or _name_from_entity_id(entity_id)

        if not entity_id or not node_type:
            continue

        if node_type in {"query_result", "result"}:
            continue

        target = _target_from_node(entity_id=entity_id, node_type=node_type, label=label)
        if target and target.entity_id not in seen:
            targets.append(target)
            seen.add(target.entity_id)

    return targets


def _target_from_node(entity_id: str, node_type: str, label: str) -> SourceLocationTarget | None:
    normalized_type = node_type.lower()

    if normalized_type in {"output_column", "column"} and entity_id.startswith("output_column:"):
        return SourceLocationTarget(entity_id, "output_column", label, "select_output")

    if normalized_type in {"physical_table", "table"} and entity_id.startswith("physical_table:"):
        return SourceLocationTarget(entity_id, "physical_table", label, "table_reference")

    if normalized_type == "cte" and entity_id.startswith("cte:"):
        return SourceLocationTarget(entity_id, "cte", label, "cte_definition")

    return None


def _graph_nodes(graph: Any) -> Iterable[Any]:
    if graph is None:
        return []
    if isinstance(graph, dict):
        return graph.get("nodes") or []
    return getattr(graph, "nodes", []) or []


def _node_get(node: Any, key: str) -> Any:
    if isinstance(node, dict):
        return node.get(key)
    return getattr(node, key, None)


def _name_from_entity_id(entity_id: str | None) -> str:
    if not entity_id:
        return ""
    return entity_id.split(":", 1)[-1]
