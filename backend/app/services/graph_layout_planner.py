from __future__ import annotations

from collections import defaultdict

from app.domain.graph_layout_models import LayoutConfig, LayoutEdge, LayoutNode, LayoutResult
from app.domain.graph_view_model import GraphEdge, GraphModel, GraphNode
from app.services.graph_crossing_minimizer import CrossingMinimizer
from app.services.graph_semantic_layering import LaneAssigner, SemanticLayerAssigner


class GraphLayoutPlanner:
    def __init__(self, config: LayoutConfig | None = None):
        self.config = config or LayoutConfig()
        self.semantic_layering = SemanticLayerAssigner()
        self.lane_assigner = LaneAssigner()
        self.crossing_minimizer = CrossingMinimizer(self.config)

    def plan(self, nodes: list[LayoutNode], edges: list[LayoutEdge]) -> LayoutResult:
        self.semantic_layering.assign(nodes)
        self._enforce_dependency_ranks(nodes, edges)
        self._attach_downstream_outputs(nodes, edges)
        self.lane_assigner.assign(nodes)
        nodes = self.crossing_minimizer.minimize(nodes, edges)
        self._assign_positions(nodes)
        self._assign_port_orders(nodes, edges)
        return LayoutResult(nodes=nodes, edges=edges, layout_hint=self._layout_hint())

    def plan_graph_model(self, graph: GraphModel) -> GraphModel:
        nodes = [_layout_node_from_graph_node(node, index) for index, node in enumerate(graph.nodes)]
        edges = [_layout_edge_from_graph_edge(edge) for edge in graph.edges]
        result = self.plan(nodes, edges)
        layout_by_id = {node.id: node for node in result.nodes}
        edge_by_key = {(edge.source, edge.target, edge.edge_type): edge for edge in result.edges}

        planned_nodes = []
        for node in graph.nodes:
            layout = layout_by_id[node.id]
            planned_nodes.append(
                GraphNode(
                    id=node.id,
                    node_type=node.node_type,
                    label=node.label,
                    entity_id=node.entity_id,
                    rank=layout.rank,
                    lane=layout.lane,
                    semantic_role=layout.semantic_role,
                    order_in_rank=layout.order_in_rank,
                    cluster_id=layout.cluster_id,
                    position={"x": layout.x, "y": layout.y},
                    layout_locked=False,
                )
            )

        planned_edges = []
        for edge in graph.edges:
            layout_edge = edge_by_key.get((edge.source, edge.target, edge.edge_type))
            planned_edges.append(
                GraphEdge(
                    id=edge.id,
                    source=edge.source,
                    target=edge.target,
                    edge_type=edge.edge_type,
                    source_port_order=layout_edge.source_port_order if layout_edge else None,
                    target_port_order=layout_edge.target_port_order if layout_edge else None,
                )
            )

        return GraphModel(
            view_mode=graph.view_mode,
            nodes=planned_nodes,
            edges=planned_edges,
            layout_hint=result.layout_hint,
        )

    def _assign_positions(self, nodes: list[LayoutNode]) -> None:
        by_rank: dict[int, list[LayoutNode]] = defaultdict(list)
        for node in nodes:
            by_rank[node.rank if node.rank is not None else self.config.default_rank].append(node)
        for rank, rank_nodes in by_rank.items():
            rank_nodes.sort(key=lambda node: (node.order_in_rank, node.sql_order, node.id))
            for index, node in enumerate(rank_nodes):
                if self.config.direction == "LR":
                    node.x = rank * self.config.rank_gap
                    node.y = index * self.config.node_gap
                else:
                    node.x = index * self.config.node_gap
                    node.y = rank * self.config.rank_gap

    def _enforce_dependency_ranks(self, nodes: list[LayoutNode], edges: list[LayoutEdge]) -> None:
        node_by_id = {node.id: node for node in nodes}
        for _ in range(len(nodes)):
            changed = False
            for edge in edges:
                source = node_by_id.get(edge.source)
                target = node_by_id.get(edge.target)
                if source is None or target is None:
                    continue
                source_rank = source.rank if source.rank is not None else self.config.default_rank
                target_rank = target.rank if target.rank is not None else self.config.default_rank
                required_rank = source_rank + 1
                if target_rank < required_rank:
                    target.rank = required_rank
                    changed = True
            if not changed:
                return

    def _assign_port_orders(self, nodes: list[LayoutNode], edges: list[LayoutEdge]) -> None:
        node_order = {node.id: node.order_in_rank for node in nodes}
        outgoing: dict[str, list[LayoutEdge]] = defaultdict(list)
        incoming: dict[str, list[LayoutEdge]] = defaultdict(list)
        for edge in edges:
            outgoing[edge.source].append(edge)
            incoming[edge.target].append(edge)
        for source, source_edges in outgoing.items():
            source_edges.sort(key=lambda edge: (node_order.get(edge.target, 0), edge.target, edge.edge_type))
            for index, edge in enumerate(source_edges):
                edge.source_port_order = index
        for target, target_edges in incoming.items():
            target_edges.sort(key=lambda edge: (node_order.get(edge.source, 0), edge.source, edge.edge_type))
            for index, edge in enumerate(target_edges):
                edge.target_port_order = index

    def _attach_downstream_outputs(self, nodes: list[LayoutNode], edges: list[LayoutEdge]) -> None:
        output_ids = {node.id for node in nodes if node.node_type in {"output_column", "output_field", "output"}}
        downstream: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            if edge.target in output_ids:
                downstream[edge.source].add(edge.target)
        for node in nodes:
            if downstream.get(node.id):
                node.data["downstream_outputs"] = sorted(downstream[node.id])

    def _layout_hint(self) -> dict:
        return {
            "algorithm": f"semantic-layered-{self.config.score_method}",
            "direction": self.config.direction,
            "rank_gap": self.config.rank_gap,
            "node_gap": self.config.node_gap,
            "lane_gap": self.config.lane_gap,
            "crossing_minimization": f"weighted_{self.config.score_method}_sweep",
            "iterations": self.config.iterations,
            "preserve_sql_order_within_group": self.config.preserve_sql_order,
        }


def _layout_node_from_graph_node(node: GraphNode, index: int) -> LayoutNode:
    return LayoutNode(
        id=node.id,
        node_type=node.node_type,
        semantic_role=node.semantic_role or "unknown",
        rank=node.rank,
        lane=node.lane,
        sql_order=index,
        order_in_rank=node.order_in_rank or 0,
        x=(node.position or {}).get("x") if node.position else None,
        y=(node.position or {}).get("y") if node.position else None,
        cluster_id=node.cluster_id,
        data={"label": node.label},
    )


def _layout_edge_from_graph_edge(edge: GraphEdge) -> LayoutEdge:
    return LayoutEdge(source=edge.source, target=edge.target, edge_type=edge.edge_type)
