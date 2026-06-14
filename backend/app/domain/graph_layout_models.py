from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any, Literal

ScoreMethod = Literal["barycenter", "median"]
Direction = Literal["LR", "TB"]


@dataclass
class LayoutNode:
    id: str
    node_type: str = "unknown"
    semantic_role: str = "unknown"
    rank: int | None = None
    lane: str | None = None
    sql_order: int = 0
    order_in_rank: int = 0
    width: float = 160.0
    height: float = 48.0
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
    source_port_order: int | None = None
    target_port_order: int | None = None


@dataclass
class LayoutConfig:
    direction: Direction = "LR"
    score_method: ScoreMethod = "barycenter"
    iterations: int = 4
    rank_gap: float = 260.0
    node_gap: float = 76.0
    lane_gap: float = 140.0
    preserve_sql_order: bool = True
    use_lane_grouping: bool = True
    default_rank: int = 2


@dataclass
class LayoutResult:
    nodes: list[LayoutNode]
    edges: list[LayoutEdge]
    layout_hint: dict[str, Any]


def edge_weight(edge: LayoutEdge) -> float:
    if edge.weight is not None:
        return edge.weight
    weights = {
        "column_lineage": 5.0,
        "value_lineage": 5.0,
        "output_column_to_result": 4.0,
        "table_to_cte": 3.0,
        "cte_dependency": 3.0,
        "cte_to_result": 3.0,
        "subquery_dependency": 3.0,
        "table_to_result": 2.0,
        "expression_dependency": 4.0,
        "expression_to_output": 4.0,
        "diagnostic": 0.5,
    }
    return weights.get(edge.edge_type, 1.0)


def weighted_barycenter(items: list[tuple[int, float]]) -> float | None:
    if not items:
        return None
    total = sum(weight for _, weight in items)
    if total <= 0:
        return None
    return sum(position * weight for position, weight in items) / total


def weighted_median(items: list[tuple[int, float]]) -> float | None:
    if not items:
        return None
    expanded: list[float] = []
    for position, weight in items:
        expanded.extend([float(position)] * max(1, int(round(weight))))
    return float(median(expanded))
