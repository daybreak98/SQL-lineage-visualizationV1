from __future__ import annotations

from app.domain.graph_view_model import GraphEdge, GraphModel, GraphNode
from app.services.cte_structure_service import CteStructureResult
from app.domain.lineage_model import SimpleColumnLineage
from app.services.graph_layout_planner import GraphLayoutPlanner
from app.services.table_structure_service import TableStructureResult


def build_column_lineage_graph(lineages: list[SimpleColumnLineage]) -> GraphModel:
    graph = GraphModel(view_mode="column")
    seen_node_ids: set[str] = set()
    seen_edge_ids: set[str] = set()
    result_id = "query_result:final"

    _add_node_once(
        graph,
        seen_node_ids,
        GraphNode(
            id=result_id,
            node_type="output",
            label="Query Result",
        ),
    )

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

        result_edge = GraphEdge(
            id=f"edge:{target_id}->{result_id}",
            source=target_id,
            target=result_id,
            edge_type="output_column_to_result",
        )
        if result_edge.id not in seen_edge_ids:
            graph.edges.append(result_edge)
            seen_edge_ids.add(result_edge.id)

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
    return GraphLayoutPlanner().plan_graph_model(merged)


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


# ── C09 expression graph building ─────────────────────────

def build_expression_graph(
    metrics: list[dict],
    existing_nodes: list[dict],
    existing_edges: list[dict],
) -> tuple[list[dict], list[dict]]:
    node_ids: set[str] = {n.get("id", "") for n in existing_nodes}
    edge_ids: set[str] = {e.get("id", "") for e in existing_edges}
    extra_nodes: list[dict] = []
    extra_edges: list[dict] = []

    for metric in metrics:
        name = metric["name"]
        expr_id = f"expression:{name}"
        output_id = f"output_column:{name}"

        if expr_id not in node_ids:
            extra_nodes.append({
                "id": expr_id,
                "entity_id": expr_id,
                "node_type": "expression",
                "label": f"{name} expression",
                "data": {
                    "name": name,
                    "expression": metric.get("expression"),
                    "depends_on": metric.get("depends_on", []),
                    "aggregate_functions": metric.get("aggregate_functions", []),
                    "operators": metric.get("operators", []),
                    "function_names": metric.get("function_names", []),
                    "description": metric.get("description"),
                    "confidence_level": metric.get("confidence_level", "high"),
                },
            })
            node_ids.add(expr_id)

        for dep in metric.get("depends_on", []):
            source_id = f"physical_column:{dep}"
            if source_id not in node_ids:
                extra_nodes.append({
                    "id": source_id,
                    "entity_id": f"column:{dep}",
                    "node_type": "physical_column",
                    "label": dep,
                })
                node_ids.add(source_id)

            edge_id = f"edge:{source_id}->{expr_id}:expression_dependency"
            if edge_id not in edge_ids:
                extra_edges.append({
                    "id": edge_id,
                    "source": source_id,
                    "target": expr_id,
                    "edge_type": "expression_dependency",
                    "label": "depends",
                })
                edge_ids.add(edge_id)

        edge_id = f"edge:{expr_id}->{output_id}:expression_to_output"
        if edge_id not in edge_ids:
            extra_edges.append({
                "id": edge_id,
                "source": expr_id,
                "target": output_id,
                "edge_type": "expression_to_output",
                "label": "produces",
            })
            edge_ids.add(edge_id)

    return extra_nodes, extra_edges
