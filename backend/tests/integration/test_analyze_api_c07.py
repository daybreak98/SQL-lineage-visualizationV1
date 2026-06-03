from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _payload(version: str | None = None) -> dict:
    return {
        "metadata_version": version or f"c07-{uuid4().hex[:8]}",
        "tables": [
            {
                "catalog": "default",
                "schema": "default",
                "table_name": "dwd_order_di",
                "comment": "order table",
                "columns": [
                    {"name": "order_no", "data_type": "string", "comment": "order number"},
                    {"name": "user_id", "data_type": "string", "comment": "user id"},
                    {"name": "order_amount", "data_type": "double", "comment": "order amount"},
                ],
            },
            {
                "catalog": "default",
                "schema": "default",
                "table_name": "dim_user_df",
                "comment": "user dim",
                "columns": [
                    {"name": "user_id", "data_type": "string", "comment": "user id"},
                    {"name": "country_name", "data_type": "string", "comment": "country"},
                ],
            },
        ],
    }


def _commit():
    client.post("/api/metadata/import/commit", json={"mode": "commit", "payload": _payload()})


def test_select_star_with_metadata_expands_all_columns():
    _commit()
    resp = client.post("/api/sql/analyze", json={"sql": "select * from dwd_order_di"})
    data = resp.json()

    assert data["status"] in ("success", "partial")
    nodes = data["graph_view_model"]["nodes"]
    output_cols = [n for n in nodes if n["node_type"] == "output_column"]
    assert len(output_cols) == 3
    col_names = {n["label"] for n in output_cols}
    assert col_names == {"order_no", "user_id", "order_amount"}


def test_select_star_without_metadata_returns_diagnostic():
    resp = client.post("/api/sql/analyze", json={"sql": "select * from no_such_table"})
    data = resp.json()

    assert data["status"] == "partial"
    star_diags = {d["code"] for d in data["diagnostics_report"]["diagnostics"]}
    assert star_diags & {"SELECT_STAR_METADATA_REQUIRED", "METADATA_MISSING"}


def test_unknown_column_with_metadata():
    _commit()
    resp = client.post("/api/sql/analyze", json={"sql": "select nonexistent_col from dwd_order_di"})
    data = resp.json()

    assert data["status"] == "partial"
    assert any(
        d["code"] == "UNKNOWN_COLUMN"
        for d in data["diagnostics_report"]["diagnostics"]
    )
    column_edges = [e for e in data["graph_view_model"]["edges"] if e["edge_type"] == "column_lineage"]
    assert len(column_edges) == 0


def test_ambiguous_column_with_metadata_disambiguation():
    _commit()
    resp = client.post("/api/sql/analyze", json={
        "sql": "select u.country_name, u.user_id from dim_user_df u join dwd_order_di o on u.user_id = o.user_id"
    })
    data = resp.json()

    assert data["status"] in ("success", "partial")
    output_cols = {n["label"] for n in data["graph_view_model"]["nodes"] if n["node_type"] == "output_column"}
    assert "country_name" in output_cols
    assert "user_id" in output_cols


def test_unqualified_column_auto_disambiguated_by_metadata():
    _commit()
    resp = client.post("/api/sql/analyze", json={
        "sql": "select country_name from dim_user_df u join dwd_order_di o on u.user_id = o.user_id"
    })
    data = resp.json()

    assert data["status"] in ("success", "partial")
    edges = data["graph_view_model"]["edges"]
    column_edges = [e for e in edges if e["edge_type"] == "column_lineage"]
    assert any("dim_user_df.country_name" in e["source"] for e in column_edges)


def test_star_and_regular_mixed():
    _commit()
    resp = client.post("/api/sql/analyze", json={
        "sql": "select *, count(order_no) as cnt from dwd_order_di"
    })
    data = resp.json()

    assert data["status"] in ("success", "partial")
    output_cols = {n["label"] for n in data["graph_view_model"]["nodes"] if n["node_type"] == "output_column"}
    assert "order_no" in output_cols
    assert "user_id" in output_cols
    assert "order_amount" in output_cols


def test_partial_metadata_no_false_disambiguation():
    """select user_id from t1 join t2 — t1 has metadata, t2 does not → must not guess"""
    version = f"c07-partial-{uuid4().hex[:8]}"
    client.post("/api/metadata/import/commit", json={"mode": "commit", "payload": {
        "metadata_version": version,
        "tables": [
            {
                "catalog": "default", "schema": "default",
                "table_name": "t1",
                "columns": [{"name": "user_id", "data_type": "string"}],
            },
        ],
    }})
    resp = client.post("/api/sql/analyze", json={
        "sql": "select user_id from t1 join t2 on t1.id = t2.id"
    })
    data = resp.json()

    assert data["status"] == "partial"
    assert any(
        d["code"] == "AMBIGUOUS_COLUMN"
        for d in data["diagnostics_report"]["diagnostics"]
    )


def test_all_metadata_but_column_unknown():
    """select nonexistent from t1 join t2 — both have metadata, column not found → UNKNOWN_COLUMN"""
    version = f"c07-unknown-{uuid4().hex[:8]}"
    client.post("/api/metadata/import/commit", json={"mode": "commit", "payload": {
        "metadata_version": version,
        "tables": [
            {"catalog": "default", "schema": "default", "table_name": "t1", "columns": [{"name": "a", "data_type": "string"}]},
            {"catalog": "default", "schema": "default", "table_name": "t2", "columns": [{"name": "b", "data_type": "string"}]},
        ],
    }})
    resp = client.post("/api/sql/analyze", json={
        "sql": "select nonexistent from t1 join t2 on t1.a = t2.b"
    })
    data = resp.json()

    assert data["status"] == "partial"
    assert any(
        d["code"] == "UNKNOWN_COLUMN"
        for d in data["diagnostics_report"]["diagnostics"]
    )
