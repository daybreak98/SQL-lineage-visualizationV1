import unittest

from src.sql_lineage_layout.crossing_minimizer import CrossingMinimizer
from src.sql_lineage_layout.demo_case import build_intl_ab_metric_demo
from src.sql_lineage_layout.models import LayoutConfig, LayoutEdge, LayoutNode
from src.sql_lineage_layout.semantic_layering import LaneAssigner, SemanticLayerAssigner


class CrossingMinimizerTest(unittest.TestCase):
    def test_weighted_barycenter_orders_outputs_by_source(self):
        nodes, edges = build_intl_ab_metric_demo()
        SemanticLayerAssigner().assign(nodes)
        LaneAssigner().assign(nodes)
        minimized = CrossingMinimizer(LayoutConfig(score_method="barycenter", iterations=4)).minimize(nodes, edges)

        outputs = [n for n in minimized if n.rank == 4]
        order = {n.id: n.order_in_rank for n in outputs}

        self.assertLess(order["S2D"], order["单UV收益"])
        self.assertLess(order["S2O"], order["单UV收益"])
        self.assertLess(order["单UV收益"], order["订单ADR"])
        self.assertLess(order["曝光与订单adr_gap"], order["订单ADR"])

    def test_median_is_robust_to_outlier_dependency(self):
        nodes = [
            LayoutNode(id="A", node_type="cte", rank=0, sql_order=0),
            LayoutNode(id="B", node_type="cte", rank=0, sql_order=1),
            LayoutNode(id="C", node_type="cte", rank=0, sql_order=2),
            LayoutNode(id="Outlier", node_type="cte", rank=0, sql_order=100),
            LayoutNode(id="X", node_type="output_column", rank=1, sql_order=0),
        ]
        edges = [
            LayoutEdge(source="A", target="X"),
            LayoutEdge(source="B", target="X"),
            LayoutEdge(source="C", target="X"),
            LayoutEdge(source="Outlier", target="X"),
        ]
        minimized = CrossingMinimizer(LayoutConfig(score_method="median", iterations=1)).minimize(nodes, edges)
        x = next(n for n in minimized if n.id == "X")
        self.assertEqual(x.rank, 1)
        self.assertEqual(x.order_in_rank, 0)

    def test_crossing_counter_detects_simple_crossing(self):
        upper = [LayoutNode(id="A", rank=0), LayoutNode(id="B", rank=0)]
        lower = [LayoutNode(id="Y", rank=1), LayoutNode(id="X", rank=1)]
        edges = [LayoutEdge(source="A", target="X"), LayoutEdge(source="B", target="Y")]
        crossings = CrossingMinimizer.count_crossings_between_layers(upper, lower, edges)
        self.assertEqual(crossings, 1)


if __name__ == "__main__":
    unittest.main()
