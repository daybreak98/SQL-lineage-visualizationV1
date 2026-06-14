import unittest

from src.sql_lineage_layout.models import LayoutNode
from src.sql_lineage_layout.port_order_optimizer import PortOrderOptimizer


class PortOrderOptimizerTest(unittest.TestCase):
    def test_port_order_follows_downstream_output_order(self):
        node = LayoutNode(
            id="search_result",
            fields=["show_uv", "click_uv", "order_uv", "show_pv", "click_pv"],
        )
        target_positions = {
            "S2D": 0,
            "S2O": 1,
            "搜索点击率_pv": 2,
        }
        field_to_targets = {
            "click_uv": ["S2D"],
            "show_uv": ["S2D", "S2O"],
            "order_uv": ["S2O"],
            "click_pv": ["搜索点击率_pv"],
            "show_pv": ["搜索点击率_pv"],
        }
        ordered = PortOrderOptimizer().optimize(node, field_to_targets, target_positions)

        self.assertLess(ordered.index("click_uv"), ordered.index("click_pv"))
        self.assertLess(ordered.index("show_uv"), ordered.index("show_pv"))
        self.assertEqual(node.field_order, ordered)


if __name__ == "__main__":
    unittest.main()
