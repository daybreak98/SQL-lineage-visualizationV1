from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ScoreMethod = Literal["barycenter", "median"]
Direction = Literal["LR", "TB"]
NodeType = Literal[
    "physical_table",
    "source_column",
    "cte",
    "subquery",
    "output_column",
    "expression",
    "unknown",
]
SemanticRole = Literal[
    "physical_table",
    "source_column",
    "base_cte",
    "enrich_cte",
    "aggregate_cte",
    "output_column",
    "expression",
    "unknown",
]


@dataclass
class LayoutNode:
    """A graph node with semantic layout metadata.

    This model is intentionally independent of SQLGlot and frontend libraries.
    It can be adapted from the existing GraphViewModel node structure.
    """

    id: str
    node_type: NodeType = "unknown"
    semantic_role: SemanticRole = "unknown"
    rank: int | None = None
    lane: str | None = None
    sql_order: int = 0
    order_in_rank: int = 0
    width: float = 220.0
    height: float = 72.0
    x: float | None = None
    y: float | None = None
    cluster_id: str | None = None
    fields: list[str] = field(default_factory=list)
    field_order: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class LayoutEdge:
    source: str
    target: str
    edge_type: str = "value_lineage"
    weight: float | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class LayoutConfig:
    direction: Direction = "LR"
    score_method: ScoreMethod = "barycenter"
    iterations: int = 4
    rank_gap: float = 360.0
    node_gap: float = 96.0
    lane_gap: float = 180.0
    preserve_sql_order: bool = True
    use_lane_grouping: bool = True
    default_rank: int = 2


@dataclass
class LayoutResult:
    nodes: list[LayoutNode]
    edges: list[LayoutEdge]
    layout_hint: dict[str, Any]


def edge_weight(edge: LayoutEdge) -> float:
    """Default edge weights for SQL lineage layout.

    Main value lineage should dominate layout. Filters and diagnostics should not
    pull nodes away from the primary dependency direction.
    """

    if edge.weight is not None:
        return edge.weight

    defaults = {
        "value_lineage": 5.0,
        "aggregate_input": 4.0,
        "join_key": 3.0,
        "group_by": 2.0,
        "filter": 1.0,
        "diagnostic": 0.5,
    }
    return defaults.get(edge.edge_type, 1.0)
