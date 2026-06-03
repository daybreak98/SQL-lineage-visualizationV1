from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

GOLDEN_PAYLOAD = {
    "metadata_version": "golden-001",
    "tables": [
        {
            "catalog": "default",
            "schema": "default",
            "table_name": "dwd_order_di",
            "comment": "order detail",
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
                {"name": "country_name", "data_type": "string", "comment": "country name"},
            ],
        },
    ],
}


def _preview(payload):
    return client.post("/api/metadata/import/preview", json={"mode": "preview", "payload": payload})


def _commit(payload):
    return client.post("/api/metadata/import/commit", json={"mode": "commit", "payload": payload})


def test_preview_returns_preview_ready():
    resp = _preview(GOLDEN_PAYLOAD)
    assert resp.status_code == 200
    assert resp.json()["status"] == "preview_ready"


def test_preview_summary_has_table_and_column_count():
    resp = _preview(GOLDEN_PAYLOAD)
    data = resp.json()
    assert data["summary"]["table_count"] == 2
    assert data["summary"]["column_count"] == 5


def test_preview_does_not_write():
    resp = _preview(GOLDEN_PAYLOAD)
    assert resp.json()["import_batch_id"] is None


def test_commit_returns_committed():
    resp = _commit({"metadata_version": "c06-commit-test", "tables": GOLDEN_PAYLOAD["tables"]})
    assert resp.status_code == 200
    assert resp.json()["status"] == "committed"


def test_commit_produces_batch_id():
    resp = _commit({"metadata_version": "c06-batch-test", "tables": GOLDEN_PAYLOAD["tables"]})
    assert resp.json()["import_batch_id"] is not None


def test_duplicate_commit_is_safe():
    version = "c06-dup-test"
    _commit({"metadata_version": version, "tables": GOLDEN_PAYLOAD["tables"]})
    resp = _commit({"metadata_version": version, "tables": GOLDEN_PAYLOAD["tables"]})
    diag = resp.json()["diagnostics"]
    assert any(d["code"] == "METADATA_VERSION_EXISTS" for d in diag)


def test_list_tables_returns_c06_table():
    _commit({"metadata_version": "c06-list-test", "tables": GOLDEN_PAYLOAD["tables"]})
    resp = client.get("/api/metadata/tables")
    names = [t["table_name"] for t in resp.json()["tables"]]
    assert "dwd_order_di" in names
    assert "dim_user_df" in names


def test_list_columns_returns_columns():
    _commit({"metadata_version": "c06-col-test", "tables": GOLDEN_PAYLOAD["tables"]})
    resp = client.get("/api/metadata/columns?table_name=dwd_order_di")
    names = [c["name"] for c in resp.json()["columns"]]
    assert "order_no" in names
    assert "order_amount" in names


def test_list_columns_returns_comment():
    _commit({"metadata_version": "c06-comment-test", "tables": GOLDEN_PAYLOAD["tables"]})
    resp = client.get("/api/metadata/columns?table_name=dim_user_df")
    by_name = {c["name"]: c for c in resp.json()["columns"]}
    assert by_name["country_name"]["comment"] == "country name"
