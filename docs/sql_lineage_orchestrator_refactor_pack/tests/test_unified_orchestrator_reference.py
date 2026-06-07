"""
Reference tests for unified CTE / non-CTE orchestration.

These are not guaranteed drop-in tests. Adapt fixtures/client imports to the current project.
"""

import pytest


@pytest.mark.integration
def test_non_cte_single_table_lineage_not_regressed(client):
    sql = """
    select order_id as order_no
    from dwd_order_di
    """
    resp = client.post("/api/sql/analyze", json={"sql": sql, "dialect": "spark"})
    assert resp.status_code == 200
    data = resp.json()

    nodes = data["graph_view_model"]["nodes"]
    edges = data["graph_view_model"]["edges"]

    assert any(n["id"] == "physical_table:dwd_order_di" for n in nodes)
    assert any(n["id"] == "output_column:order_no" for n in nodes)
    assert any(e["target"] == "output_column:order_no" for e in edges)


@pytest.mark.integration
def test_non_cte_join_lineage_not_regressed(client):
    sql = """
    select
        o.order_id,
        u.user_name
    from dwd_order_di o
    join dim_user u on o.user_id = u.user_id
    """
    resp = client.post("/api/sql/analyze", json={"sql": sql, "dialect": "spark"})
    assert resp.status_code == 200
    data = resp.json()

    node_ids = {n["id"] for n in data["graph_view_model"]["nodes"]}
    assert "physical_table:dwd_order_di" in node_ids
    assert "physical_table:dim_user" in node_ids
    assert "output_column:order_id" in node_ids
    assert "output_column:user_name" in node_ids


@pytest.mark.integration
def test_cte_structure_graph_exists(client):
    sql = """
    with order_base as (
        select order_id, user_id
        from dwd_order_di
    )
    select order_id
    from order_base
    """
    resp = client.post("/api/sql/analyze", json={"sql": sql, "dialect": "spark"})
    assert resp.status_code == 200
    data = resp.json()

    node_ids = {n["id"] for n in data["graph_view_model"]["nodes"]}
    assert "physical_table:dwd_order_di" in node_ids
    assert "cte:order_base" in node_ids
    assert "query_result:final" in node_ids


@pytest.mark.integration
def test_cte_final_hop_column_lineage_exists(client):
    sql = """
    with order_base as (
        select order_id, user_id
        from dwd_order_di
    )
    select order_id as order_no
    from order_base
    """
    resp = client.post("/api/sql/analyze", json={"sql": sql, "dialect": "spark"})
    assert resp.status_code == 200
    data = resp.json()

    edges = data["graph_view_model"]["edges"]
    assert any(
        e["source"] in {"column:order_base.order_id", "cte_column:order_base.order_id"}
        and e["target"] == "output_column:order_no"
        for e in edges
    )


@pytest.mark.integration
def test_cte_name_should_not_be_loaded_as_metadata(client, monkeypatch):
    """Adapt this test to spy on _load_metadata or metadata_repository.

    Expected: metadata lookup receives only physical table names, not CTE names.
    """
    # Pseudocode:
    # seen = []
    # monkeypatch.setattr(analyze_controller, "_load_metadata", lambda names: seen.extend(names) or {})
    # ... call analyze ...
    # assert "dwd_order_di" in seen
    # assert "order_base" not in seen
    pass


@pytest.mark.integration
def test_cte_plus_join_final_select(client):
    sql = """
    with order_base as (
        select order_id, user_id
        from dwd_order_di
    )
    select
        ob.order_id,
        u.user_name
    from order_base ob
    join dim_user u on ob.user_id = u.user_id
    """
    resp = client.post("/api/sql/analyze", json={"sql": sql, "dialect": "spark"})
    assert resp.status_code == 200
    data = resp.json()

    node_ids = {n["id"] for n in data["graph_view_model"]["nodes"]}
    assert "cte:order_base" in node_ids
    assert "physical_table:dim_user" in node_ids
    assert "output_column:order_id" in node_ids
    assert "output_column:user_name" in node_ids

    capabilities = data.get("capabilities") or {}
    if "cte_end_to_end_column_lineage" in capabilities:
        assert capabilities["cte_end_to_end_column_lineage"] is False
