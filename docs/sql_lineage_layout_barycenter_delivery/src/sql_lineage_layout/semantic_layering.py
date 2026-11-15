from __future__ import annotations

from .models import LayoutNode


class SemanticLayerAssigner:
    """Assign SQL semantic rank and role to nodes.

    In a production project, this should use parser/lineage metadata rather than
    pure name heuristics. The heuristics here are only safe defaults for initial
    integration and tests.
    """

    def assign(self, nodes: list[LayoutNode]) -> None:
        for node in nodes:
            self.assign_one(node)

    def assign_one(self, node: LayoutNode) -> LayoutNode:
        if node.rank is not None and node.semantic_role != "unknown":
            return node

        if node.node_type == "physical_table":
            node.semantic_role = "physical_table"
            node.rank = 0 if node.rank is None else node.rank
            return node

        if node.node_type == "source_column":
            node.semantic_role = "source_column"
            node.rank = 0 if node.rank is None else node.rank
            return node

        if node.node_type == "output_column":
            node.semantic_role = "output_column"
            node.rank = 4 if node.rank is None else node.rank
            return node

        if node.node_type == "expression":
            node.semantic_role = "expression"
            node.rank = 4 if node.rank is None else node.rank
            return node

        if node.node_type == "cte":
            name = node.id.lower()
            # Prefer explicit data flags when present.
            if node.data.get("has_aggregate"):
                node.semantic_role = "aggregate_cte"
                node.rank = 3 if node.rank is None else node.rank
                return node
            if node.data.get("has_window") or node.data.get("has_join"):
                node.semantic_role = "enrich_cte"
                node.rank = 2 if node.rank is None else node.rank
                return node

            # Initial heuristics for the supplied SQL case.
            if name in {"search_result", "order_result", "order_90"} or name.endswith("_result"):
                node.semantic_role = "aggregate_cte"
                node.rank = 3 if node.rank is None else node.rank
            elif name in {"search_list", "order_detail", "product"}:
                node.semantic_role = "enrich_cte"
                node.rank = 2 if node.rank is None else node.rank
            else:
                node.semantic_role = "base_cte"
                node.rank = 1 if node.rank is None else node.rank
            return node

        node.semantic_role = "unknown"
        node.rank = 2 if node.rank is None else node.rank
        return node


class LaneAssigner:
    """Assign vertical lanes.

    Production implementation should derive lane from downstream output columns.
    This implementation combines explicit hints and cautious heuristics.
    """

    LANE_PRIORITY = {
        "search_branch": 0,
        "mixed_branch": 1,
        "order_branch": 2,
        "ab_branch": 3,
        "dimension_branch": 4,
        "shared_branch": 5,
        "default": 6,
    }

    def assign(self, nodes: list[LayoutNode]) -> None:
        for node in nodes:
            self.assign_one(node)

    def assign_one(self, node: LayoutNode) -> LayoutNode:
        if node.lane:
            return node

        name = node.id.lower()
        outputs = {str(x).lower() for x in node.data.get("downstream_outputs", [])}

        if name == "ab_rule":
            node.lane = "ab_branch"
        elif name in {"user_type", "hotel_info", "product"}:
            node.lane = "dimension_branch"
        elif self._has_search_signal(name, outputs):
            node.lane = "search_branch"
        elif self._has_order_signal(name, outputs):
            node.lane = "order_branch"
        elif self._has_mixed_signal(outputs):
            node.lane = "mixed_branch"
        else:
            node.lane = "shared_branch"

        return node

    def lane_priority(self, lane: str | None) -> int:
        return self.LANE_PRIORITY.get(lane or "default", self.LANE_PRIORITY["default"])

    def _has_search_signal(self, name: str, outputs: set[str]) -> bool:
        if "search" in name or "show" in name or "click" in name:
            return True
        return any(
            token in out
            for out in outputs
            for token in ["搜索", "s2", "click", "曝光", "无库存", "无结果", "top"]
        )

    def _has_order_signal(self, name: str, outputs: set[str]) -> bool:
        if "order" in name:
            return True
        return any(token in out for out in outputs for token in ["订单", "gmv", "adr", "收益"])

    def _has_mixed_signal(self, outputs: set[str]) -> bool:
        has_search = any(token in out for out in outputs for token in ["搜索", "曝光", "s2", "click"])
        has_order = any(token in out for out in outputs for token in ["订单", "adr", "收益"])
        return has_search and has_order
