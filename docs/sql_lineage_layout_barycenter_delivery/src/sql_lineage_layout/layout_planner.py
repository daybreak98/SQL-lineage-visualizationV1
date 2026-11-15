from __future__ import annotations

from collections import defaultdict

from .crossing_minimizer import CrossingMinimizer
from .models import LayoutConfig, LayoutEdge, LayoutNode, LayoutResult
from .semantic_layering import LaneAssigner, SemanticLayerAssigner


class GraphLayoutPlanner:
    """Plan semantic layered layout for SQL lineage graph.

    It only adds layout metadata. It must not alter lineage semantics.
    """

    def __init__(self, config: LayoutConfig | None = None):
        self.config = config or LayoutConfig()
        self.semantic_layering = SemanticLayerAssigner()
        self.lane_assigner = LaneAssigner()
        self.crossing_minimizer = CrossingMinimizer(self.config)

    def plan(self, nodes: list[LayoutNode], edges: list[LayoutEdge]) -> LayoutResult:
        self.semantic_layering.assign(nodes)
        self.lane_assigner.assign(nodes)
        nodes = self.crossing_minimizer.minimize(nodes, edges)
        self._assign_positions(nodes)
        return LayoutResult(
            nodes=nodes,
            edges=edges,
            layout_hint={
                "algorithm": f"semantic-layered-{self.config.score_method}",
                "direction": self.config.direction,
                "rank_gap": self.config.rank_gap,
                "node_gap": self.config.node_gap,
                "lane_gap": self.config.lane_gap,
                "crossing_minimization": f"weighted_{self.config.score_method}_sweep",
                "iterations": self.config.iterations,
                "preserve_sql_order_within_group": self.config.preserve_sql_order,
            },
        )

    def _assign_positions(self, nodes: list[LayoutNode]) -> None:
        by_rank: dict[int, list[LayoutNode]] = defaultdict(list)
        for node in nodes:
            by_rank[node.rank if node.rank is not None else self.config.default_rank].append(node)

        # Stable y order within rank already set by crossing minimizer.
        for rank, layer_nodes in by_rank.items():
            layer_nodes.sort(key=lambda n: (n.order_in_rank, n.sql_order, n.id))
            for index, node in enumerate(layer_nodes):
                if self.config.direction == "LR":
                    node.x = rank * self.config.rank_gap
                    node.y = index * self.config.node_gap
                else:
                    node.x = index * self.config.node_gap
                    node.y = rank * self.config.rank_gap

    @staticmethod
    def to_graph_view_model(result: LayoutResult) -> dict:
        return {
            "nodes": [
                {
                    "id": node.id,
                    "type": node.node_type,
                    "rank": node.rank,
                    "lane": node.lane,
                    "semantic_role": node.semantic_role,
                    "order_in_rank": node.order_in_rank,
                    "cluster_id": node.cluster_id,
                    "position": {"x": node.x, "y": node.y},
                    "data": {
                        **node.data,
                        "field_order": node.field_order or node.fields,
                    },
                }
                for node in result.nodes
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "type": edge.edge_type,
                    "weight": edge.weight,
                    "data": edge.data,
                }
                for edge in result.edges
            ],
            "layout_hint": result.layout_hint,
        }
