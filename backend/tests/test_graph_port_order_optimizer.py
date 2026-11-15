from app.domain.graph_layout_models import LayoutNode
from app.services.graph_port_order_optimizer import PortOrderOptimizer


def test_port_order_follows_downstream_output_order():
    node = LayoutNode(
        id="search_result",
        fields=["show_uv", "click_uv", "order_uv", "show_pv", "click_pv"],
    )
    target_positions = {
        "s2d": 0,
        "s2o": 1,
        "search_click_rate_pv": 2,
    }
    field_to_targets = {
        "click_uv": ["s2d"],
        "show_uv": ["s2d", "s2o"],
        "order_uv": ["s2o"],
        "click_pv": ["search_click_rate_pv"],
        "show_pv": ["search_click_rate_pv"],
    }

    ordered = PortOrderOptimizer().optimize(node, field_to_targets, target_positions)

    assert ordered.index("click_uv") < ordered.index("click_pv")
    assert ordered.index("show_uv") < ordered.index("show_pv")
    assert node.field_order == ordered
