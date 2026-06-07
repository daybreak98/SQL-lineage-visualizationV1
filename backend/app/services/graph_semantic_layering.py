from __future__ import annotations

from app.domain.graph_layout_models import LayoutNode


class SemanticLayerAssigner:
    def assign(self, nodes: list[LayoutNode]) -> None:
        for node in nodes:
            self.assign_one(node)

    def assign_one(self, node: LayoutNode) -> LayoutNode:
        if node.rank is not None and node.semantic_role != "unknown":
            return node

        node_type = node.node_type
        if node_type in {"table", "physical_table"}:
            node.semantic_role = "physical_table"
            node.rank = 0 if node.rank is None else node.rank
        elif node_type == "physical_column":
            node.semantic_role = "source_column"
            node.rank = 0 if node.rank is None else node.rank
        elif node_type == "cte":
            node.semantic_role = _cte_role(node)
            node.rank = {"base_cte": 1, "enrich_cte": 2, "aggregate_cte": 3}[node.semantic_role]
        elif node_type in {"subquery", "expression"}:
            node.semantic_role = node_type
            node.rank = 2 if node.rank is None else node.rank
        elif node_type in {"output_column", "output_field"}:
            node.semantic_role = "output_column"
            node.rank = 4 if node.rank is None else node.rank
        elif node_type == "output":
            node.semantic_role = "query_result"
            node.rank = 5 if node.rank is None else node.rank
        else:
            node.semantic_role = "unknown"
            node.rank = 2 if node.rank is None else node.rank
        return node


class LaneAssigner:
    LANE_PRIORITY = {
        "search_branch": 0,
        "mixed_branch": 1,
        "order_branch": 2,
        "dimension_branch": 3,
        "shared_branch": 4,
        "default": 5,
    }

    def assign(self, nodes: list[LayoutNode]) -> None:
        for node in nodes:
            self.assign_one(node)

    def assign_one(self, node: LayoutNode) -> LayoutNode:
        if node.lane:
            return node
        text = " ".join([node.id, str(node.data.get("label", "")), " ".join(map(str, node.data.get("downstream_outputs", [])))]).lower()
        has_search = any(token in text for token in ["search", "click", "s2d", "s2o"])
        has_order = any(token in text for token in ["order", "gmv", "adr", "amount"])
        if has_search and has_order:
            node.lane = "mixed_branch"
        elif has_search:
            node.lane = "search_branch"
        elif has_order:
            node.lane = "order_branch"
        elif node.semantic_role == "physical_table":
            node.lane = "shared_branch"
        else:
            node.lane = "default"
        return node

    def lane_priority(self, lane: str | None) -> int:
        return self.LANE_PRIORITY.get(lane or "default", self.LANE_PRIORITY["default"])


def _cte_role(node: LayoutNode) -> str:
    data = node.data
    name = node.id.lower()
    if data.get("has_aggregate") or name.endswith("_result") or "metric" in name:
        return "aggregate_cte"
    if data.get("has_join") or data.get("has_window") or "join" in name or "enrich" in name:
        return "enrich_cte"
    return "base_cte"
