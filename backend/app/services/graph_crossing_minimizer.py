from __future__ import annotations

from collections import defaultdict
from typing import Literal

from app.domain.graph_layout_models import (
    LayoutConfig,
    LayoutEdge,
    LayoutNode,
    edge_weight,
    weighted_barycenter,
    weighted_median,
)
from app.services.graph_semantic_layering import LaneAssigner

SweepDirection = Literal["left_to_right", "right_to_left"]


class CrossingMinimizer:
    def __init__(self, config: LayoutConfig | None = None):
        self.config = config or LayoutConfig()
        self.lane_assigner = LaneAssigner()

    def minimize(self, nodes: list[LayoutNode], edges: list[LayoutEdge]) -> list[LayoutNode]:
        layers = self._group_by_rank(nodes)
        ranks = sorted(layers)

        for _ in range(max(1, self.config.iterations)):
            for current_rank in ranks[1:]:
                previous_rank = self._previous_existing_rank(ranks, current_rank)
                if previous_rank is None:
                    continue
                layers[current_rank] = self._sort_layer_by_neighbors(
                    layer_nodes=layers[current_rank],
                    neighbor_positions=self._position_map(layers[previous_rank]),
                    edges=edges,
                    direction="left_to_right",
                )
            for current_rank in reversed(ranks[:-1]):
                next_rank = self._next_existing_rank(ranks, current_rank)
                if next_rank is None:
                    continue
                layers[current_rank] = self._sort_layer_by_neighbors(
                    layer_nodes=layers[current_rank],
                    neighbor_positions=self._position_map(layers[next_rank]),
                    edges=edges,
                    direction="right_to_left",
                )

        result: list[LayoutNode] = []
        for rank in sorted(layers):
            for index, node in enumerate(layers[rank]):
                node.order_in_rank = index
                result.append(node)
        return result

    def _group_by_rank(self, nodes: list[LayoutNode]) -> dict[int, list[LayoutNode]]:
        layers: dict[int, list[LayoutNode]] = defaultdict(list)
        for node in nodes:
            rank = node.rank if node.rank is not None else self.config.default_rank
            node.rank = rank
            layers[rank].append(node)
        for layer_nodes in layers.values():
            layer_nodes.sort(key=self._stable_initial_key)
            for index, node in enumerate(layer_nodes):
                node.order_in_rank = index
        return dict(layers)

    def _stable_initial_key(self, node: LayoutNode):
        lane_key = self.lane_assigner.lane_priority(node.lane) if self.config.use_lane_grouping else 0
        return (lane_key, node.order_in_rank, node.sql_order, node.id)

    def _sort_layer_by_neighbors(
        self,
        layer_nodes: list[LayoutNode],
        neighbor_positions: dict[str, int],
        edges: list[LayoutEdge],
        direction: SweepDirection,
    ) -> list[LayoutNode]:
        scored: list[tuple[int, float, int, str, LayoutNode]] = []
        for node in layer_nodes:
            score = self._score(self._collect_neighbor_items(node, neighbor_positions, edges, direction))
            if score is None:
                score = float(node.order_in_rank)
            lane_key = self.lane_assigner.lane_priority(node.lane) if self.config.use_lane_grouping else 0
            scored.append((lane_key, score, node.sql_order, node.id, node))
        sorted_nodes = [item[-1] for item in sorted(scored, key=lambda item: (item[0], item[1], item[2], item[3]))]
        for index, node in enumerate(sorted_nodes):
            node.order_in_rank = index
        return sorted_nodes

    def _collect_neighbor_items(
        self,
        node: LayoutNode,
        neighbor_positions: dict[str, int],
        edges: list[LayoutEdge],
        direction: SweepDirection,
    ) -> list[tuple[int, float]]:
        items: list[tuple[int, float]] = []
        for edge in edges:
            if direction == "left_to_right" and edge.target == node.id and edge.source in neighbor_positions:
                items.append((neighbor_positions[edge.source], edge_weight(edge)))
            if direction == "right_to_left" and edge.source == node.id and edge.target in neighbor_positions:
                items.append((neighbor_positions[edge.target], edge_weight(edge)))
        return items

    def _score(self, items: list[tuple[int, float]]) -> float | None:
        if self.config.score_method == "median":
            return weighted_median(items)
        return weighted_barycenter(items)

    @staticmethod
    def _position_map(layer_nodes: list[LayoutNode]) -> dict[str, int]:
        return {node.id: index for index, node in enumerate(layer_nodes)}

    @staticmethod
    def _previous_existing_rank(ranks: list[int], current_rank: int) -> int | None:
        previous = [rank for rank in ranks if rank < current_rank]
        return previous[-1] if previous else None

    @staticmethod
    def _next_existing_rank(ranks: list[int], current_rank: int) -> int | None:
        following = [rank for rank in ranks if rank > current_rank]
        return following[0] if following else None

    @staticmethod
    def count_crossings_between_layers(
        upper_layer: list[LayoutNode],
        lower_layer: list[LayoutNode],
        edges: list[LayoutEdge],
    ) -> int:
        upper_pos = {node.id: index for index, node in enumerate(upper_layer)}
        lower_pos = {node.id: index for index, node in enumerate(lower_layer)}
        layer_edges = [
            (upper_pos[edge.source], lower_pos[edge.target])
            for edge in edges
            if edge.source in upper_pos and edge.target in lower_pos
        ]
        crossings = 0
        for i, first in enumerate(layer_edges):
            for second in layer_edges[i + 1:]:
                if (first[0] - second[0]) * (first[1] - second[1]) < 0:
                    crossings += 1
        return crossings
