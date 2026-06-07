import unittest

from src.sql_lineage_layout.demo_case import build_intl_ab_metric_demo
from src.sql_lineage_layout.layout_planner import GraphLayoutPlanner
from src.sql_lineage_layout.models import LayoutConfig


class GraphLayoutPlannerTest(unittest.TestCase):
    def test_layout_planner_outputs_rank_lane_position(self):
        nodes, edges = build_intl_ab_metric_demo()
        result = GraphLayoutPlanner(LayoutConfig(iterations=4)).plan(nodes, edges)
        by_id = {n.id: n for n in result.nodes}

        self.assertEqual(by_id["search_result"].rank, 3)
        self.assertEqual(by_id["order_result"].rank, 3)
        self.assertEqual(by_id["S2D"].rank, 4)
        self.assertIsNotNone(by_id["S2D"].x)
        self.assertIsNotNone(by_id["S2D"].y)
        self.assertEqual(result.layout_hint["direction"], "LR")

    def test_to_graph_view_model_contains_layout_hint(self):
        nodes, edges = build_intl_ab_metric_demo()
        planner = GraphLayoutPlanner(LayoutConfig(iterations=2))
        result = planner.plan(nodes, edges)
        graph = planner.to_graph_view_model(result)

        self.assertIn("layout_hint", graph)
        self.assertIn("nodes", graph)
        self.assertTrue(all("position" in n for n in graph["nodes"]))


if __name__ == "__main__":
    unittest.main()
