from fastapi.testclient import TestClient

from app.main import app


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


def test_group_by_field_is_an_explicit_group_dependency():
    graph = _graph("select count(*) as cnt from orders group by region")
    clause = "clause:group_by:query_result:final:1"

    assert {
        ("physical_column:orders.region", clause, "group_dependency"),
        (clause, "query_result:final", "group_effect"),
    } <= _edges(graph)


def test_order_by_non_projected_field_is_an_explicit_order_dependency():
    graph = _graph("select id from orders order by created_at desc")
    clause = "clause:order_by:query_result:final:1"

    assert {
        ("physical_column:orders.created_at", clause, "order_dependency"),
        (clause, "query_result:final", "order_effect"),
    } <= _edges(graph)


def test_order_by_alias_expands_projection_inputs_without_fake_column():
    graph = _graph(
        "select amount * tax_rate as gross_amount "
        "from order_items order by gross_amount desc"
    )
    clause = "clause:order_by:query_result:final:1"
    edges = _edges(graph)

    assert {
        ("physical_column:order_items.amount", clause, "order_dependency"),
        ("physical_column:order_items.tax_rate", clause, "order_dependency"),
    } <= edges
    assert all(
        source != "physical_column:order_items.gross_amount"
        for source, _, _ in edges
    )


def test_group_and_order_ordinals_expand_projection_inputs():
    graph = _graph(
        "select region, event_date, count(*) as cnt "
        "from orders group by 1, 2 order by 2 desc"
    )
    group_clause = "clause:group_by:query_result:final:1"
    order_clause = "clause:order_by:query_result:final:1"

    assert {
        (
            "physical_column:orders.region",
            group_clause,
            "group_dependency",
        ),
        (
            "physical_column:orders.event_date",
            group_clause,
            "group_dependency",
        ),
        (
            "physical_column:orders.event_date",
            order_clause,
            "order_dependency",
        ),
    } <= _edges(graph)


def test_cte_group_field_rolls_up_to_physical_column():
    graph = _graph(
        "with grouped as ("
        "select customer_id, region, count(*) as cnt "
        "from orders group by customer_id, region"
        ") select customer_id, cnt from grouped order by cnt desc"
    )
    group_clause = "clause:group_by:cte:grouped:1"

    assert {
        (
            "physical_column:orders.customer_id",
            group_clause,
            "group_dependency",
        ),
        (
            "physical_column:orders.region",
            group_clause,
            "group_dependency",
        ),
        (group_clause, "cte:grouped", "group_effect"),
    } <= _edges(graph)


def test_distribute_and_sort_fields_are_explicit_clause_dependencies():
    graph = _graph(
        "select id from events "
        "distribute by tenant_id sort by event_time desc"
    )
    distribute = "clause:distribute_by:query_result:final:1"
    sort = "clause:sort_by:query_result:final:1"

    assert {
        (
            "physical_column:events.tenant_id",
            distribute,
            "distribute_dependency",
        ),
        (distribute, "query_result:final", "distribute_effect"),
        (
            "physical_column:events.event_time",
            sort,
            "sort_dependency",
        ),
        (sort, "query_result:final", "sort_effect"),
    } <= _edges(graph)


def test_cluster_by_field_is_an_explicit_clause_dependency():
    graph = _graph("select id from events cluster by tenant_id")
    cluster = "clause:cluster_by:query_result:final:1"

    assert {
        (
            "physical_column:events.tenant_id",
            cluster,
            "cluster_dependency",
        ),
        (cluster, "query_result:final", "cluster_effect"),
    } <= _edges(graph)


def test_sort_by_alias_and_ordinal_expand_projection_inputs():
    alias_graph = _graph(
        "select amount * tax_rate as gross_amount "
        "from order_items sort by gross_amount desc"
    )
    ordinal_graph = _graph(
        "select id, created_at from events sort by 2 desc"
    )
    alias_clause = "clause:sort_by:query_result:final:1"
    ordinal_clause = "clause:sort_by:query_result:final:1"

    assert {
        (
            "physical_column:order_items.amount",
            alias_clause,
            "sort_dependency",
        ),
        (
            "physical_column:order_items.tax_rate",
            alias_clause,
            "sort_dependency",
        ),
    } <= _edges(alias_graph)
    assert (
        "physical_column:events.created_at",
        ordinal_clause,
        "sort_dependency",
    ) in _edges(ordinal_graph)


def test_cte_distribution_field_rolls_up_to_physical_column():
    graph = _graph(
        "with prepared as (select id, tenant_id from raw_events) "
        "select id from prepared distribute by tenant_id"
    )
    distribute = "clause:distribute_by:query_result:final:1"

    assert (
        "physical_column:raw_events.tenant_id",
        distribute,
        "distribute_dependency",
    ) in _edges(graph)
