from __future__ import annotations

from .models import LayoutEdge, LayoutNode


def build_intl_ab_metric_demo() -> tuple[list[LayoutNode], list[LayoutEdge]]:
    """A small graph extracted from the supplied AB metric SQL.

    This is not a parser. It is a deterministic golden-case graph for testing
    layout behavior around search_result / order_result / final outputs.
    """

    nodes = [
        LayoutNode(id="search_result", node_type="cte", sql_order=0, data={"has_aggregate": True}),
        LayoutNode(id="order_result", node_type="cte", sql_order=1, data={"has_aggregate": True}),
        LayoutNode(id="单UV收益", node_type="output_column", sql_order=0),
        LayoutNode(id="S2D", node_type="output_column", sql_order=1),
        LayoutNode(id="S2O", node_type="output_column", sql_order=2),
        LayoutNode(id="搜索点击率_pv", node_type="output_column", sql_order=3),
        LayoutNode(id="搜索预定率_pv", node_type="output_column", sql_order=4),
        LayoutNode(id="搜索无结果率", node_type="output_column", sql_order=5),
        LayoutNode(id="无库存流量占比", node_type="output_column", sql_order=6),
        LayoutNode(id="订单ADR", node_type="output_column", sql_order=16),
        LayoutNode(id="曝光ADR", node_type="output_column", sql_order=17),
        LayoutNode(id="曝光与订单adr_gap", node_type="output_column", sql_order=18),
    ]

    edges = [
        LayoutEdge(source="search_result", target="单UV收益", edge_type="value_lineage"),
        LayoutEdge(source="order_result", target="单UV收益", edge_type="value_lineage"),
        LayoutEdge(source="search_result", target="S2D", edge_type="value_lineage"),
        LayoutEdge(source="search_result", target="S2O", edge_type="value_lineage"),
        LayoutEdge(source="search_result", target="搜索点击率_pv", edge_type="value_lineage"),
        LayoutEdge(source="search_result", target="搜索预定率_pv", edge_type="value_lineage"),
        LayoutEdge(source="search_result", target="搜索无结果率", edge_type="value_lineage"),
        LayoutEdge(source="search_result", target="无库存流量占比", edge_type="value_lineage"),
        LayoutEdge(source="order_result", target="订单ADR", edge_type="value_lineage"),
        LayoutEdge(source="search_result", target="曝光ADR", edge_type="value_lineage"),
        LayoutEdge(source="search_result", target="曝光与订单adr_gap", edge_type="value_lineage"),
        LayoutEdge(source="order_result", target="曝光与订单adr_gap", edge_type="value_lineage"),
    ]
    return nodes, edges
