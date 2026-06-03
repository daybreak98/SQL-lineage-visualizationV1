from app.services.cte_structure_service import analyze_cte_structure
from app.services.graph_builder import build_cte_structure_graph


GOLDEN_CTE_SQL = """with order_base as (
  select
    user_id,
    order_no,
    order_amount
  from dwd_order_di
),
metric_base as (
  select
    user_id,
    count(order_no) as order_cnt,
    sum(order_amount) as gmv
  from order_base
  group by user_id
)
select
  user_id,
  order_cnt,
  gmv
from metric_base"""


def test_cte_structure_extracts_nodes():
    result = analyze_cte_structure(GOLDEN_CTE_SQL)

    assert result.status == "success"
    assert result.confidence_level == "medium"
    assert {node.id for node in result.nodes} == {
        "physical_table:dwd_order_di",
        "cte:order_base",
        "cte:metric_base",
        "query_result:final",
    }


def test_cte_structure_extracts_dependency_edges():
    result = analyze_cte_structure(GOLDEN_CTE_SQL)

    assert {(edge.source, edge.target, edge.edge_type) for edge in result.edges} == {
        ("physical_table:dwd_order_di", "cte:order_base", "table_to_cte"),
        ("cte:order_base", "cte:metric_base", "cte_dependency"),
        ("cte:metric_base", "query_result:final", "cte_to_result"),
    }


def test_cte_structure_graph_uses_subquery_dependency_view():
    result = analyze_cte_structure(GOLDEN_CTE_SQL)
    graph = build_cte_structure_graph(result).to_dict()

    assert graph["view_mode"] == "subquery_dependency"
    node_ids = {node["id"] for node in graph["nodes"]}
    assert "cte:order_base" in node_ids
    assert "cte:metric_base" in node_ids
    assert "query_result:final" in node_ids
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in graph["edges"])


def test_non_cte_query_returns_partial():
    result = analyze_cte_structure("select a from t")

    assert result.status == "partial"
    assert result.nodes == []
    assert result.edges == []
    assert "non_cte_query" in result.unsupported_features
