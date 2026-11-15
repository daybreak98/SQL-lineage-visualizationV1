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


def test_where_fields_are_explicit_predicate_dependencies():
    graph = _graph(
        "select o.id from orders o "
        "where o.status = 'PAID' and o.amount > 100"
    )
    predicate = "predicate:where:query_result:final:1"

    assert {
        ("physical_column:orders.status", predicate, "predicate_dependency"),
        ("physical_column:orders.amount", predicate, "predicate_dependency"),
        (predicate, "query_result:final", "predicate_effect"),
    } <= _edges(graph)


def test_join_condition_fields_use_join_dependencies():
    graph = _graph(
        "select o.id from orders o "
        "join customers c on o.customer_id = c.id and c.active = 1"
    )
    predicate = "predicate:join:query_result:final:1"

    assert {
        ("physical_column:orders.customer_id", predicate, "join_dependency"),
        ("physical_column:customers.id", predicate, "join_dependency"),
        ("physical_column:customers.active", predicate, "join_dependency"),
        (predicate, "query_result:final", "join_effect"),
    } <= _edges(graph)


def test_correlated_exists_fields_attach_to_predicate_subquery():
    graph = _graph(
        "select o.id from orders o where exists ("
        "select 1 from refunds r "
        "where r.order_id = o.id and r.status = 'APPROVED'"
        ")"
    )
    predicate = "predicate:where:subquery:exists_subquery_1:1"

    assert {
        ("physical_column:refunds.order_id", predicate, "predicate_dependency"),
        ("physical_column:orders.id", predicate, "predicate_dependency"),
        ("physical_column:refunds.status", predicate, "predicate_dependency"),
        (predicate, "subquery:exists_subquery_1", "predicate_effect"),
    } <= _edges(graph)


def test_cte_predicate_field_rolls_up_to_physical_column():
    graph = _graph(
        "with filtered as (select id, status from orders) "
        "select id from filtered where status = 'PAID'"
    )
    predicate = "predicate:where:query_result:final:1"

    assert (
        "physical_column:orders.status",
        predicate,
        "predicate_dependency",
    ) in _edges(graph)


def test_qualify_output_alias_expands_window_source_columns():
    graph = _graph(
        "select o.id, row_number() over ("
        "partition by o.customer_id order by o.created_at"
        ") as rn from orders o qualify rn = 1"
    )
    predicate = "predicate:qualify:query_result:final:1"
    edges = _edges(graph)

    assert {
        (
            "physical_column:orders.customer_id",
            predicate,
            "predicate_dependency",
        ),
        (
            "physical_column:orders.created_at",
            predicate,
            "predicate_dependency",
        ),
    } <= edges
    assert all(source != "physical_column:orders.rn" for source, _, _ in edges)


def test_having_output_alias_expands_aggregate_source_column():
    graph = _graph(
        "select o.customer_id, sum(o.amount) as total_amount "
        "from orders o group by o.customer_id having total_amount > 100"
    )
    predicate = "predicate:having:query_result:final:1"
    edges = _edges(graph)

    assert (
        "physical_column:orders.amount",
        predicate,
        "predicate_dependency",
    ) in edges
    assert all(
        source != "physical_column:orders.total_amount"
        for source, _, _ in edges
    )


def test_multiple_in_subqueries_keep_source_order_owner_ids():
    graph = _graph(
        "select o.id from orders o where o.id in ("
        "select p.order_id from payments p where p.status = 'SETTLED'"
        ") and o.id in ("
        "select r.order_id from refunds r where r.status = 'APPROVED'"
        ")"
    )
    edges = _edges(graph)
    first = "predicate:where:subquery:in_subquery_1:1"
    second = "predicate:where:subquery:in_subquery_2:1"

    assert {
        (
            "physical_column:payments.status",
            first,
            "predicate_dependency",
        ),
        (first, "subquery:in_subquery_1", "predicate_effect"),
        (
            "physical_column:refunds.status",
            second,
            "predicate_dependency",
        ),
        (second, "subquery:in_subquery_2", "predicate_effect"),
    } <= edges


def test_in_subquery_projection_key_affects_outer_predicate():
    graph = _graph(
        "select o.id from orders o where o.id in ("
        "select r.order_id from refunds r where r.status = 'APPROVED'"
        ")"
    )
    outer = "predicate:where:query_result:final:1"

    assert (
        "physical_column:refunds.order_id",
        outer,
        "predicate_dependency",
    ) in _edges(graph)


def test_tuple_in_subquery_projection_keys_affect_outer_predicate():
    graph = _graph(
        "select o.id from orders o where "
        "(o.customer_id, o.store_id) in ("
        "select b.customer_id, b.store_id from blacklist b"
        ")"
    )
    outer = "predicate:where:query_result:final:1"

    assert {
        (
            "physical_column:blacklist.customer_id",
            outer,
            "predicate_dependency",
        ),
        (
            "physical_column:blacklist.store_id",
            outer,
            "predicate_dependency",
        ),
    } <= _edges(graph)


def test_scalar_subquery_projection_affects_outer_predicate():
    graph = _graph(
        "select o.id from orders o where o.amount > ("
        "select avg(p.amount) from payments p "
        "where p.order_id = o.id"
        ")"
    )
    outer = "predicate:where:query_result:final:1"

    assert (
        "physical_column:payments.amount",
        outer,
        "predicate_dependency",
    ) in _edges(graph)


def test_scalar_count_subquery_adds_inner_rowset_to_outer_predicate():
    graph = _graph(
        "select o.id from orders o where ("
        "select count(*) from payments p where p.order_id = o.id"
        ") > 0"
    )
    outer = "predicate:where:query_result:final:1"

    assert (
        "physical_column:payments.*",
        outer,
        "predicate_dependency",
    ) in _edges(graph)


def test_set_operation_subquery_keys_affect_outer_predicate():
    graph = _graph(
        "select o.id from orders o where o.id in ("
        "select r.order_id from refunds r "
        "union all "
        "select c.order_id from chargebacks c"
        ")"
    )
    outer = "predicate:where:query_result:final:1"

    assert {
        (
            "physical_column:refunds.order_id",
            outer,
            "predicate_dependency",
        ),
        (
            "physical_column:chargebacks.order_id",
            outer,
            "predicate_dependency",
        ),
    } <= _edges(graph)


def test_exists_projection_does_not_affect_existence_predicate():
    graph = _graph(
        "select o.id from orders o where exists ("
        "select r.internal_note from refunds r "
        "where r.order_id = o.id"
        ")"
    )
    outer = "predicate:where:query_result:final:1"

    assert (
        "physical_column:refunds.internal_note",
        outer,
        "predicate_dependency",
    ) not in _edges(graph)
