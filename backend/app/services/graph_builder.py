from __future__ import annotations

from app.domain.graph_view_model import GraphEdge, GraphModel, GraphNode
from app.services.cte_structure_service import CteStructureResult
from app.domain.lineage_model import SimpleColumnLineage
from app.services.table_structure_service import TableStructureResult


def build_column_lineage_graph(lineages: list[SimpleColumnLineage]) -> GraphModel:
    graph = GraphModel(view_mode="column")
    seen_node_ids: set[str] = set()
    seen_edge_ids: set[str] = set()

    for lineage in lineages:
        source_id = f"physical_column:{lineage.source_label}"
        target_id = f"output_column:{lineage.output_column}"

        _add_node_once(
            graph,
            seen_node_ids,
            GraphNode(
                id=source_id,
                node_type="physical_column",
                label=lineage.source_label,
            ),
        )
        _add_node_once(
            graph,
            seen_node_ids,
            GraphNode(
                id=target_id,
                node_type="output_column",
                label=lineage.output_column,
            ),
        )

        edge = GraphEdge(
            id=f"edge:{source_id}->{target_id}",
            source=source_id,
            target=target_id,
            edge_type="column_lineage",
        )
        if edge.id not in seen_edge_ids:
            graph.edges.append(edge)
            seen_edge_ids.add(edge.id)

    validate_graph(graph)
    return graph


def build_cte_structure_graph(structure: CteStructureResult) -> GraphModel:
    graph = GraphModel(view_mode="subquery_dependency")
    _append_structure_graph(graph, structure.nodes, structure.edges)
    validate_graph(graph)
    return graph


def build_table_structure_graph(structure: TableStructureResult) -> GraphModel:
    graph = GraphModel(view_mode="table")
    _append_structure_graph(graph, structure.nodes, structure.edges)
    validate_graph(graph)
    return graph


def merge_graphs(view_mode: str, *graphs: GraphModel) -> GraphModel:
    merged = GraphModel(view_mode=view_mode)
    seen_node_ids: set[str] = set()
    seen_edge_ids: set[str] = set()

    for graph in graphs:
        for node in graph.nodes:
            _add_node_once(merged, seen_node_ids, node)
        for edge in graph.edges:
            if edge.id not in seen_edge_ids:
                merged.edges.append(edge)
                seen_edge_ids.add(edge.id)

    validate_graph(merged)
    return merged


def _append_structure_graph(graph: GraphModel, nodes, edges) -> None:
    seen_node_ids: set[str] = set()
    seen_edge_ids: set[str] = set()

    for node in nodes:
        _add_node_once(
            graph,
            seen_node_ids,
            GraphNode(
                id=node.id,
                node_type=node.node_type,
                label=node.label,
            ),
        )

    for edge in edges:
        graph_edge = GraphEdge(
            id=edge.id,
            source=edge.source,
            target=edge.target,
            edge_type=edge.edge_type,
        )
        if graph_edge.id not in seen_edge_ids:
            graph.edges.append(graph_edge)
            seen_edge_ids.add(graph_edge.id)


def validate_graph(graph: GraphModel) -> None:
    node_ids = {node.id for node in graph.nodes}
    for edge in graph.edges:
        if not edge.source or not edge.target:
            raise ValueError(f"Graph edge {edge.id} has empty source or target.")
        if edge.source not in node_ids:
            raise ValueError(f"Graph edge {edge.id} source {edge.source} does not exist.")
        if edge.target not in node_ids:
            raise ValueError(f"Graph edge {edge.id} target {edge.target} does not exist.")


def _add_node_once(graph: GraphModel, seen_node_ids: set[str], node: GraphNode) -> None:
    if node.id in seen_node_ids:
        return
    graph.nodes.append(node)
    seen_node_ids.add(node.id)
