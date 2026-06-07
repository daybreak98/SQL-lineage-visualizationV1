from __future__ import annotations

from .models import LayoutEdge, LayoutNode


class GraphViewModelAdapter:
    """Convert between existing dict-based GraphViewModel and layout models."""

    @staticmethod
    def from_graph_view_model(graph: dict) -> tuple[list[LayoutNode], list[LayoutEdge]]:
        nodes: list[LayoutNode] = []
        for idx, raw in enumerate(graph.get("nodes", [])):
            data = raw.get("data", {}) or {}
            nodes.append(
                LayoutNode(
                    id=raw["id"],
                    node_type=raw.get("node_type") or raw.get("type") or "unknown",
                    semantic_role=raw.get("semantic_role", "unknown"),
                    rank=raw.get("rank"),
                    lane=raw.get("lane"),
                    sql_order=raw.get("sql_order", data.get("sql_order", idx)),
                    order_in_rank=raw.get("order_in_rank", 0),
                    fields=data.get("fields", []),
                    data=data,
                )
            )

        edges: list[LayoutEdge] = []
        for raw in graph.get("edges", []):
            edges.append(
                LayoutEdge(
                    source=raw["source"],
                    target=raw["target"],
                    edge_type=raw.get("edge_type") or raw.get("type") or "value_lineage",
                    weight=raw.get("weight"),
                    data=raw.get("data", {}) or {},
                )
            )
        return nodes, edges

    @staticmethod
    def merge_layout(graph: dict, layout_graph: dict) -> dict:
        layout_by_id = {node["id"]: node for node in layout_graph.get("nodes", [])}
        merged_nodes = []
        for raw in graph.get("nodes", []):
            updated = dict(raw)
            layout = layout_by_id.get(raw["id"])
            if layout:
                updated.update(
                    {
                        "rank": layout.get("rank"),
                        "lane": layout.get("lane"),
                        "semantic_role": layout.get("semantic_role"),
                        "order_in_rank": layout.get("order_in_rank"),
                        "position": layout.get("position"),
                    }
                )
                data = dict(updated.get("data", {}) or {})
                data.update(layout.get("data", {}) or {})
                updated["data"] = data
            merged_nodes.append(updated)

        result = dict(graph)
        result["nodes"] = merged_nodes
        result["layout_hint"] = layout_graph.get("layout_hint", {})
        return result
