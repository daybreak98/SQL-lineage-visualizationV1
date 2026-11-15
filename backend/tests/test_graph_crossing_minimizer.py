from app.domain.graph_layout_models import LayoutConfig, LayoutEdge, LayoutNode
from app.services.graph_crossing_minimizer import CrossingMinimizer


def test_weighted_barycenter_orders_outputs_by_source():
    nodes = [
        LayoutNode(id="search_result", node_type="cte", rank=0, sql_order=0),
        LayoutNode(id="order_result", node_type="cte", rank=0, sql_order=1),
        LayoutNode(id="order_cnt", node_type="output_column", rank=1, sql_order=0),
        LayoutNode(id="search_click_rate", node_type="output_column", rank=1, sql_order=1),
        LayoutNode(id="search_booking_rate", node_type="output_column", rank=1, sql_order=2),
        LayoutNode(id="order_adr", node_type="output_column", rank=1, sql_order=3),
    ]
    edges = [
        LayoutEdge(source="order_result", target="order_cnt"),
        LayoutEdge(source="search_result", target="search_click_rate"),
        LayoutEdge(source="search_result", target="search_booking_rate"),
        LayoutEdge(source="order_result", target="order_adr"),
    ]

    minimized = CrossingMinimizer(LayoutConfig(iterations=4)).minimize(nodes, edges)
    order = {node.id: node.order_in_rank for node in minimized if node.rank == 1}

    assert order["search_click_rate"] < order["order_cnt"]
    assert order["search_booking_rate"] < order["order_adr"]


def test_median_is_robust_to_outlier_dependency():
    nodes = [
        LayoutNode(id="A", node_type="cte", rank=0, sql_order=0),
        LayoutNode(id="B", node_type="cte", rank=0, sql_order=1),
        LayoutNode(id="C", node_type="cte", rank=0, sql_order=2),
        LayoutNode(id="Outlier", node_type="cte", rank=0, sql_order=100),
        LayoutNode(id="metric", node_type="output_column", rank=1, sql_order=0),
    ]
    edges = [
        LayoutEdge(source="A", target="metric"),
        LayoutEdge(source="B", target="metric"),
        LayoutEdge(source="C", target="metric"),
        LayoutEdge(source="Outlier", target="metric"),
    ]

    minimized = CrossingMinimizer(LayoutConfig(score_method="median", iterations=1)).minimize(nodes, edges)
    metric = next(node for node in minimized if node.id == "metric")

    assert metric.order_in_rank == 0


def test_sweep_preserves_sql_order_as_tie_breaker():
    nodes = [
        LayoutNode(id="src", node_type="cte", rank=0, sql_order=0),
        LayoutNode(id="first_metric", node_type="output_column", rank=1, sql_order=0),
        LayoutNode(id="second_metric", node_type="output_column", rank=1, sql_order=1),
    ]
    edges = [
        LayoutEdge(source="src", target="second_metric"),
        LayoutEdge(source="src", target="first_metric"),
    ]

    minimized = CrossingMinimizer(LayoutConfig(iterations=2)).minimize(nodes, edges)
    order = {node.id: node.order_in_rank for node in minimized if node.rank == 1}

    assert order["first_metric"] < order["second_metric"]


def test_crossing_counter_detects_simple_crossing():
    upper = [LayoutNode(id="A", rank=0), LayoutNode(id="B", rank=0)]
    lower = [LayoutNode(id="Y", rank=1), LayoutNode(id="X", rank=1)]
    edges = [LayoutEdge(source="A", target="X"), LayoutEdge(source="B", target="Y")]

    crossings = CrossingMinimizer.count_crossings_between_layers(upper, lower, edges)

    assert crossings == 1
