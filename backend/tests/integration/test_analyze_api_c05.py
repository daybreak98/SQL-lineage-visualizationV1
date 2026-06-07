from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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


def test_analyze_c05_golden_cte_returns_structure_graph():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": GOLDEN_CTE_SQL, "dialect": "spark"},
    )
    data = response.json()

    assert response.status_code == 200
    assert data["schema_version"] == "0.3.0-c09"
    assert data["analysis_id"] == "analysis:c09"
    assert data["status"] == "success"
    assert data["graph_view_model"]["view_mode"] == "subquery_dependency"

    node_ids = {node["id"] for node in data["graph_view_model"]["nodes"]}
    assert {
        "physical_table:dwd_order_di",
        "cte:order_base",
        "cte:metric_base",
        "query_result:final",
    }.issubset(node_ids)

    edges = {
        (edge["source"], edge["target"], edge["edge_type"])
        for edge in data["graph_view_model"]["edges"]
    }
    assert ("physical_table:dwd_order_di", "cte:order_base", "table_to_cte") in edges
    assert ("cte:order_base", "cte:metric_base", "cte_dependency") in edges
    assert ("cte:metric_base", "query_result:final", "cte_to_result") in edges


def test_analyze_c05_cte_nodes_are_not_physical_tables():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": GOLDEN_CTE_SQL, "dialect": "spark"},
    )
    data = response.json()

    cte_nodes = [
        node
        for node in data["graph_view_model"]["nodes"]
        if node["id"].startswith("cte:")
    ]
    assert cte_nodes
    assert all(node["node_type"] == "cte" for node in cte_nodes)


def test_analyze_c05_include_graph_false_keeps_graph_empty():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": GOLDEN_CTE_SQL,
            "dialect": "spark",
            "analysis_options": {
                "include_graph": False,
                "include_semantics": False,
                "include_diagnostics": True,
                "include_source_location": True,
                "include_expression_lineage": False,
            },
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["graph_view_model"]["nodes"] == []
    assert data["graph_view_model"]["edges"] == []
