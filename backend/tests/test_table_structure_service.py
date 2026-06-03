from app.services.graph_builder import build_table_structure_graph
from app.services.table_structure_service import analyze_table_structure


def test_single_table_query_returns_table_to_result_structure():
    result = analyze_table_structure("select a from t")

    assert result.status == "success"
    assert {node.id for node in result.nodes} == {
        "physical_table:t",
        "query_result:final",
    }
    assert {(edge.source, edge.target, edge.edge_type) for edge in result.edges} == {
        ("physical_table:t", "query_result:final", "table_to_result")
    }


def test_join_query_returns_each_table_to_result_structure():
    result = analyze_table_structure(
        "select u.country_name, o.order_no "
        "from dim_user_df u "
        "join dwd_order_di o on u.user_id = o.user_id"
    )

    assert result.status == "success"
    assert {node.id for node in result.nodes} == {
        "physical_table:dim_user_df",
        "physical_table:dwd_order_di",
        "query_result:final",
    }
    assert {(edge.source, edge.target) for edge in result.edges} == {
        ("physical_table:dim_user_df", "query_result:final"),
        ("physical_table:dwd_order_di", "query_result:final"),
    }


def test_table_structure_graph_uses_table_view():
    result = analyze_table_structure("select a from t")
    graph = build_table_structure_graph(result).to_dict()

    assert graph["view_mode"] == "table"
    assert {node["id"] for node in graph["nodes"]} == {
        "physical_table:t",
        "query_result:final",
    }
    assert all(
        edge["source"] in {node["id"] for node in graph["nodes"]}
        and edge["target"] in {node["id"] for node in graph["nodes"]}
        for edge in graph["edges"]
    )
