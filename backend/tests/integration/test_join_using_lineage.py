from fastapi.testclient import TestClient
import sqlglot

from app.main import app
from app.services.predicate_dependency_service import (
    analyze_predicate_dependencies,
)


client = TestClient(app)


def _graph(sql: str) -> dict:
    response = client.post(
        "/api/sql/analyze",
        json={"sql": sql, "dialect": "spark"},
    )
    assert response.status_code == 200
    return response.json()["graph_view_model"]


def _edges(graph: dict) -> set[tuple[str, str, str]]:
    return {
        (edge["source"], edge["target"], edge["edge_type"])
        for edge in graph["edges"]
    }


def test_join_using_key_is_traced_for_both_relations():
    graph = _graph(
        "select o.id from orders o "
        "join customers c using (customer_id)"
    )
    join = "predicate:join:query_result:final:1"

    assert {
        ("physical_column:orders.customer_id", join, "join_dependency"),
        (
            "physical_column:customers.customer_id",
            join,
            "join_dependency",
        ),
        (join, "query_result:final", "join_effect"),
    } <= _edges(graph)


def test_join_using_multiple_keys_traces_every_side_and_key():
    graph = _graph(
        "select o.id from orders o join customers c "
        "using (tenant_id, customer_id)"
    )
    join = "predicate:join:query_result:final:1"

    assert {
        ("physical_column:orders.tenant_id", join, "join_dependency"),
        ("physical_column:customers.tenant_id", join, "join_dependency"),
        ("physical_column:orders.customer_id", join, "join_dependency"),
        (
            "physical_column:customers.customer_id",
            join,
            "join_dependency",
        ),
    } <= _edges(graph)


def test_chained_join_using_includes_the_accumulated_left_relations():
    graph = _graph(
        "select a.value from source_a a "
        "join source_b b using (id) "
        "join source_c c using (id)"
    )
    first = "predicate:join:query_result:final:1"
    second = "predicate:join:query_result:final:2"
    edges = _edges(graph)

    assert {
        ("physical_column:source_a.id", first, "join_dependency"),
        ("physical_column:source_b.id", first, "join_dependency"),
    } <= edges
    assert {
        ("physical_column:source_a.id", second, "join_dependency"),
        ("physical_column:source_b.id", second, "join_dependency"),
        ("physical_column:source_c.id", second, "join_dependency"),
    } <= edges


def test_cte_join_using_keys_roll_up_to_physical_columns():
    graph = _graph(
        "with order_keys as ("
        "select id, customer_id from raw_orders"
        "), customer_keys as ("
        "select customer_id, name from raw_customers"
        ") select o.id from order_keys o "
        "join customer_keys c using (customer_id)"
    )
    join = "predicate:join:query_result:final:1"

    assert {
        (
            "physical_column:raw_orders.customer_id",
            join,
            "join_dependency",
        ),
        (
            "physical_column:raw_customers.customer_id",
            join,
            "join_dependency",
        ),
    } <= _edges(graph)


def test_natural_join_keeps_rowset_dependencies_without_metadata():
    graph = _graph(
        "select o.id from orders o natural join customers c"
    )
    join = "predicate:join:query_result:final:1"

    assert {
        ("physical_column:orders.*", join, "join_dependency"),
        ("physical_column:customers.*", join, "join_dependency"),
        (join, "query_result:final", "join_effect"),
    } <= _edges(graph)


def test_natural_join_uses_exact_common_columns_when_metadata_is_available():
    tree = sqlglot.parse_one(
        "select o.order_id from orders o natural join customers c",
        dialect="spark",
    )

    dependencies = analyze_predicate_dependencies(
        tree,
        "spark",
        relation_columns={
            "orders": ["order_id", "customer_id", "created_at"],
            "customers": ["customer_id", "customer_name"],
        },
    )

    join = next(item for item in dependencies if item.predicate_kind == "join")
    roots = {column.display() for column in join.root_columns}

    assert roots == {
        "orders.customer_id",
        "customers.customer_id",
    }


def test_natural_join_cte_metadata_rolls_exact_common_key_to_physical_columns():
    graph = _graph(
        "with left_rows as ("
        "select id, tenant_id from raw_left"
        "), right_rows as ("
        "select id, display_name from raw_right"
        ") select l.tenant_id from left_rows l "
        "natural join right_rows r"
    )
    join = "predicate:join:query_result:final:1"
    edges = _edges(graph)

    assert {
        ("physical_column:raw_left.id", join, "join_dependency"),
        ("physical_column:raw_right.id", join, "join_dependency"),
    } <= edges
    assert all(
        source not in {
            "physical_column:raw_left.*",
            "physical_column:raw_right.*",
        }
        for source, target, _ in edges
        if target == join
    )


def test_unqualified_using_output_column_has_both_source_lineages():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": (
                "select customer_id from orders o "
                "join customers c using (customer_id)"
            ),
            "dialect": "spark",
        },
    )
    result = response.json()
    edges = _edges(result["graph_view_model"])

    assert result["status"] == "success"
    assert {
        (
            "physical_column:orders.customer_id",
            "output_column:customer_id",
            "column_lineage",
        ),
        (
            "physical_column:customers.customer_id",
            "output_column:customer_id",
            "column_lineage",
        ),
    } <= edges


def test_chained_using_output_column_has_all_merged_source_lineages():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": (
                "select id from source_a a "
                "join source_b b using (id) "
                "join source_c c using (id)"
            ),
            "dialect": "spark",
        },
    )
    result = response.json()
    edges = _edges(result["graph_view_model"])

    assert result["status"] == "success"
    assert {
        (
            f"physical_column:source_{suffix}.id",
            "output_column:id",
            "column_lineage",
        )
        for suffix in ("a", "b", "c")
    } <= edges


def test_cte_using_output_column_rolls_both_sources_to_physical_columns():
    graph = _graph(
        "with order_keys as ("
        "select customer_id from raw_orders"
        "), customer_keys as ("
        "select customer_id from raw_customers"
        ") select customer_id from order_keys o "
        "join customer_keys c using (customer_id)"
    )

    assert {
        (
            "physical_column:raw_orders.customer_id",
            "output_column:customer_id",
            "column_lineage",
        ),
        (
            "physical_column:raw_customers.customer_id",
            "output_column:customer_id",
            "column_lineage",
        ),
    } <= _edges(graph)


def test_natural_join_merged_output_rolls_exact_cte_sources():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": (
                "with left_rows as ("
                "select id, left_value from raw_left"
                "), right_rows as ("
                "select id, right_value from raw_right"
                ") select id from left_rows l natural join right_rows r"
            ),
            "dialect": "spark",
        },
    )
    result = response.json()

    assert result["status"] == "success"
    assert {
        (
            "physical_column:raw_left.id",
            "output_column:id",
            "column_lineage",
        ),
        (
            "physical_column:raw_right.id",
            "output_column:id",
            "column_lineage",
        ),
    } <= _edges(result["graph_view_model"])
