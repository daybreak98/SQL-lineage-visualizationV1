from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _analyze(sql: str) -> dict:
    response = client.post(
        "/api/sql/analyze",
        json={"sql": sql, "dialect": "spark"},
    )
    assert response.status_code == 200
    return response.json()


def _lineage_edges(result: dict) -> set[tuple[str, str]]:
    return {
        (edge["source"], edge["target"])
        for edge in result["graph_view_model"]["edges"]
        if edge["edge_type"] == "column_lineage"
    }


def test_count_star_is_successful_rowset_lineage():
    result = _analyze("select count(*) as cnt from orders")

    assert result["status"] == "success"
    assert result["diagnostics_report"]["warning_count"] == 0
    assert (
        "physical_column:orders.*",
        "output_column:cnt",
    ) in _lineage_edges(result)


def test_count_star_without_from_is_a_valid_source_free_aggregate():
    result = _analyze("select count(*) as cnt")

    assert result["status"] == "success"
    assert result["diagnostics_report"]["warning_count"] == 0
    assert _lineage_edges(result) == set()


def test_source_free_constant_query_is_successful():
    result = _analyze("select 1 as one, current_date() as today")

    assert result["status"] == "success"
    assert result["diagnostics_report"]["warning_count"] == 0


def test_source_free_bare_identifier_remains_unresolved():
    result = _analyze("select missing_column")

    assert result["status"] == "partial"
    assert any(
        item["code"] == "UNSUPPORTED_COMPLEX_QUERY"
        for item in result["diagnostics_report"]["diagnostics"]
    )


def test_constant_aggregate_over_join_depends_on_each_input_rowset():
    result = _analyze(
        "select count(1) as cnt from orders o "
        "join customers c on o.customer_id = c.id"
    )

    assert {
        ("physical_column:orders.*", "output_column:cnt"),
        ("physical_column:customers.*", "output_column:cnt"),
    } <= _lineage_edges(result)


def test_qualified_count_star_depends_only_on_qualified_rowset():
    result = _analyze(
        "select count(o.*) as cnt from orders o "
        "join customers c on o.customer_id = c.id"
    )
    edges = _lineage_edges(result)

    assert ("physical_column:orders.*", "output_column:cnt") in edges
    assert ("physical_column:customers.*", "output_column:cnt") not in edges


def test_cte_count_star_rolls_up_to_physical_rowset():
    result = _analyze(
        "with grouped as ("
        "select customer_id, count(*) as cnt "
        "from orders group by customer_id"
        ") select customer_id, cnt from grouped"
    )

    assert (
        "physical_column:orders.*",
        "output_column:cnt",
    ) in _lineage_edges(result)


def test_count_over_cte_rowset_rolls_up_without_fake_cte_column():
    result = _analyze(
        "with filtered as ("
        "select id from orders where status = 'PAID'"
        ") select count(*) as cnt from filtered"
    )
    edges = _lineage_edges(result)

    assert (
        "physical_column:orders.*",
        "output_column:cnt",
    ) in edges
    assert (
        "physical_column:filtered.*",
        "output_column:cnt",
    ) not in edges
    assert not any(
        item["code"] == "UNKNOWN_DERIVED_COLUMN"
        for item in result["diagnostics_report"]["diagnostics"]
    )


def test_scalar_count_star_uses_inner_query_rowset_scope():
    result = _analyze(
        "select p.id, ("
        "select count(*) from child c where c.parent_id = p.id"
        ") as child_count from parent p"
    )
    edges = _lineage_edges(result)

    assert (
        "physical_column:child.*",
        "output_column:child_count",
    ) in edges
    assert (
        "physical_column:parent.*",
        "output_column:child_count",
    ) not in edges
