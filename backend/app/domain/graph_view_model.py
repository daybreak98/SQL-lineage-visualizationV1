from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphNode:
    id: str
    node_type: str  # physical_column | output_column | table | cte | subquery ...
    label: str
    entity_id: str | None = None
    rank: int | None = None
    lane: str | None = None
    semantic_role: str | None = None
    order_in_rank: int | None = None
    cluster_id: str | None = None
    position: dict[str, float | None] | None = None
    layout_locked: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "node_type": self.node_type,
            "label": self.label,
            "entity_id": self.entity_id or self.id,
        }
        optional = {
            "rank": self.rank,
            "lane": self.lane,
            "semantic_role": self.semantic_role,
            "order_in_rank": self.order_in_rank,
            "cluster_id": self.cluster_id,
            "position": self.position,
            "layout_locked": self.layout_locked,
        }
        result.update({key: value for key, value in optional.items() if value is not None})
        return result


@dataclass
class GraphEdge:
    id: str
    source: str
    target: str
    edge_type: str  # column_lineage | subquery_dependency ...
    source_port_order: int | None = None
    target_port_order: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type,
        }
        if self.source_port_order is not None:
            result["source_port_order"] = self.source_port_order
        if self.target_port_order is not None:
            result["target_port_order"] = self.target_port_order
        return result


@dataclass
class GraphModel:
    view_mode: str = "column"
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    layout_hint: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "view_mode": self.view_mode,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "layout_hint": self.layout_hint,
        }
