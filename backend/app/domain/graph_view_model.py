from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GraphNode:
    id: str
    node_type: str  # physical_column | output_column | table | cte | subquery ...
    label: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "node_type": self.node_type, "label": self.label}


@dataclass
class GraphEdge:
    id: str
    source: str
    target: str
    edge_type: str  # column_lineage | subquery_dependency ...

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type,
        }


@dataclass
class GraphModel:
    view_mode: str = "column"
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "view_mode": self.view_mode,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }
