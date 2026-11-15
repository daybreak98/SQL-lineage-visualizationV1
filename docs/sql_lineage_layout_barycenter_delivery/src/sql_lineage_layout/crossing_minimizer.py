from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Literal

from .models import LayoutConfig, LayoutEdge, LayoutNode, edge_weight
from .semantic_layering import LaneAssigner

SweepDirection = Literal["left_to_right", "right_to_left"]


class CrossingMinimizer:
    """Sweep-based crossing minimization using weighted barycenter or median."""

    def __init__(self, config: LayoutConfig | None = None):
        self.config = config or LayoutConfig()
        self.lane_assigner = LaneAssigner()

    def minimize(self, nodes: list[LayoutNode], edges: list[LayoutEdge]) -> list[LayoutNode]:
        layers = self._group_by_rank(nodes)
        ranks = sorted(layers.keys())

        for _ in range(max(1, self.config.iterations)):
            # Left -> right sweep.
            for current_rank in ranks[1:]:
                previous_rank = self._previous_existing_rank(ranks, current_rank)
                if previous_rank is None:
                    continue
                previous_positions = self._position_map(layers[previous_rank])
                layers[current_rank] = self._sort_layer_by_neighbors(
                    layer_nodes=layers[current_rank],
                    neighbor_positions=previous_positions,
                    edges=edges,
                    direction="left_to_right",
                )

            # Right -> left sweep.
            for current_rank in reversed(ranks[:-1]):
                next_rank = self._next_existing_rank(ranks, current_rank)
                if next_rank is None:
                    continue
                next_positions = self._position_map(layers[next_rank])
                layers[current_rank] = self._sort_layer_by_neighbors(
                    layer_nodes=layers[current_rank],
                    neighbor_positions=next_positions,
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

        for rank, layer_nodes in layers.items():
            layer_nodes.sort(key=self._stable_initial_key)
            for index, node in enumerate(layer_nodes):
                node.order_in_rank = index
        return dict(layers)

    def _stable_initial_key(self, node: LayoutNode):
        lane_key = self.lane_assigner.lane_priority(node.lane) if self.config.use_lane_grouping else 0
        return (lane_key, node.order_in_rank, node.sql_order, node.id)

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

    def _sort_layer_by_neighbors(
        self,
        layer_nodes: list[LayoutNode],
        neighbor_positions: dict[str, int],
        edges: list[LayoutEdge],
        direction: SweepDirection,
    ) -> list[LayoutNode]:
        scored = []

        for node in layer_nodes:
            neighbor_items = self._collect_neighbor_items(node, neighbor_positions, edges, direction)
            score = self._score(neighbor_items)
            if score is None:
                score = float(node.order_in_rank if node.order_in_rank is not None else node.sql_order)

            lane_key = self.lane_assigner.lane_priority(node.lane) if self.config.use_lane_grouping else 0
            # Preserve SQL order as deterministic tie-breaker.
            scored.append((lane_key, score, node.sql_order, node.id, node))

        sorted_nodes = [item[-1] for item in sorted(scored, key=lambda x: (x[0], x[1], x[2], x[3]))]
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
            if direction == "left_to_right":
                if edge.target == node.id and edge.source in neighbor_positions:
                    items.append((neighbor_positions[edge.source], edge_weight(edge)))
            else:
                if edge.source == node.id and edge.target in neighbor_positions:
                    items.append((neighbor_positions[edge.target], edge_weight(edge)))
        return items

    def _score(self, neighbor_items: list[tuple[int, float]]) -> float | None:
        if not neighbor_items:
            return None
        if self.config.score_method == "median":
            weighted_positions: list[float] = []
            for position, weight in neighbor_items:
                repeats = max(1, int(round(weight)))
                weighted_positions.extend([float(position)] * repeats)
            return float(median(weighted_positions))

        total_weight = sum(weight for _, weight in neighbor_items)
        if total_weight <= 0:
            return None
        return sum(position * weight for position, weight in neighbor_items) / total_weight

    @staticmethod
    def count_crossings_between_layers(
        upper_layer: list[LayoutNode],
        lower_layer: list[LayoutNode],
        edges: list[LayoutEdge],
    ) -> int:
        """Count crossings between two adjacent layers for diagnostics/tests."""
        upper_pos = {node.id: i for i, node in enumerate(upper_layer)}
        lower_pos = {node.id: i for i, node in enumerate(lower_layer)}
        layer_edges = [
            (upper_pos[e.source], lower_pos[e.target])
            for e in edges
            if e.source in upper_pos and e.target in lower_pos
        ]
        crossings = 0
        for i in range(len(layer_edges)):
            a1, a2 = layer_edges[i]
            for j in range(i + 1, len(layer_edges)):
                b1, b2 = layer_edges[j]
                if (a1 - b1) * (a2 - b2) < 0:
                    crossings += 1
        return crossings
