from app.domain.graph_view_model import GraphEdge, GraphModel, GraphNode
from app.services.graph_layout_planner import GraphLayoutPlanner


def test_layout_planner_outputs_rank_lane_position():
    graph = GraphModel(
        view_mode="subquery_dependency",
        nodes=[
            GraphNode(id="physical_table:dwd_order_di", node_type="table", label="dwd_order_di"),
            GraphNode(id="cte:order_base", node_type="cte", label="order_base"),
            GraphNode(id="output_column:gmv", node_type="output_column", label="gmv"),
            GraphNode(id="query_result:final", node_type="output", label="Query Result"),
        ],
        edges=[
            GraphEdge(
                id="e1",
                source="physical_table:dwd_order_di",
                target="cte:order_base",
                edge_type="table_to_cte",
            ),
            GraphEdge(
                id="e2",
                source="cte:order_base",
                target="output_column:gmv",
                edge_type="column_lineage",
            ),
            GraphEdge(
                id="e3",
                source="output_column:gmv",
                target="query_result:final",
                edge_type="output_column_to_result",
            ),
        ],
    )

    planned = GraphLayoutPlanner().plan_graph_model(graph)
    by_id = {node.id: node for node in planned.nodes}

    assert by_id["physical_table:dwd_order_di"].rank == 0
    assert by_id["cte:order_base"].rank == 1
    assert by_id["output_column:gmv"].rank == 4
    assert by_id["query_result:final"].rank == 5
    assert by_id["output_column:gmv"].position["x"] > by_id["cte:order_base"].position["x"]
    assert planned.layout_hint["algorithm"] == "semantic-layered-barycenter"


def test_layout_planner_sets_edge_port_order():
    graph = GraphModel(
        nodes=[
            GraphNode(id="physical_table:t", node_type="table", label="t"),
            GraphNode(id="output_column:a", node_type="output_column", label="a"),
            GraphNode(id="output_column:b", node_type="output_column", label="b"),
        ],
        edges=[
            GraphEdge(id="edge:t->b", source="physical_table:t", target="output_column:b", edge_type="column_lineage"),
            GraphEdge(id="edge:t->a", source="physical_table:t", target="output_column:a", edge_type="column_lineage"),
        ],
    )

    planned = GraphLayoutPlanner().plan_graph_model(graph)
    edges = {edge.id: edge for edge in planned.edges}

    assert edges["edge:t->a"].source_port_order < edges["edge:t->b"].source_port_order
    assert edges["edge:t->a"].target_port_order == 0
    assert edges["edge:t->b"].target_port_order == 0


def test_layout_planner_never_places_dependent_nodes_in_same_rank():
    graph = GraphModel(
        view_mode="subquery_dependency",
        nodes=[
            GraphNode(id="physical_table:source", node_type="table", label="source"),
            GraphNode(id="cte:search_list", node_type="cte", label="search_list"),
            GraphNode(id="cte:order_detail", node_type="cte", label="order_detail"),
            GraphNode(id="cte:order_result", node_type="cte", label="order_result"),
            GraphNode(id="query_result:final", node_type="output", label="Query Result"),
        ],
        edges=[
            GraphEdge(id="e1", source="physical_table:source", target="cte:search_list", edge_type="table_to_cte"),
            GraphEdge(id="e2", source="cte:search_list", target="cte:order_detail", edge_type="cte_dependency"),
            GraphEdge(id="e3", source="cte:order_detail", target="cte:order_result", edge_type="cte_dependency"),
            GraphEdge(id="e4", source="cte:order_result", target="query_result:final", edge_type="cte_to_result"),
        ],
    )

    planned = GraphLayoutPlanner().plan_graph_model(graph)
    ranks = {node.id: node.rank for node in planned.nodes}

    for edge in planned.edges:
        assert ranks[edge.source] < ranks[edge.target], edge.id
