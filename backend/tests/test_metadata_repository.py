from pathlib import Path

from app.domain.metadata_model import ColumnMeta, TableMeta
from app.db import sqlite as sqlite_db
from app.repositories import metadata_repository as repo


def _sample_tables():
    return [
        TableMeta(
            catalog="default",
            schema="default",
            table_name="dwd_order_di",
            comment="order table",
            columns=[
                ColumnMeta(name="order_no", data_type="string", comment="order number"),
                ColumnMeta(name="user_id", data_type="string", comment="user id"),
            ],
        ),
    ]


def test_version_exists_after_import():
    version = "test-repo-v1"
    assert not repo.version_exists(version)
    repo.import_metadata(version, _sample_tables())
    assert repo.version_exists(version)


def test_pytest_uses_isolated_metadata_db():
    production_db_path = Path(sqlite_db.__file__).parent.parent.parent.parent / "data" / "metadata.db"
    assert sqlite_db.DB_PATH.name == "metadata_test.db"
    assert sqlite_db.DB_PATH != production_db_path


def test_list_tables_returns_table():
    repo.import_metadata("test-repo-v2", _sample_tables())
    tables = repo.list_tables()
    names = [t["table_name"] for t in tables]
    assert "dwd_order_di" in names


def test_get_columns_returns_columns():
    repo.import_metadata("test-repo-v3", _sample_tables())
    columns = repo.get_columns("dwd_order_di")
    names = [c["name"] for c in columns]
    assert "order_no" in names
    assert "user_id" in names


def test_column_comment_is_preserved():
    repo.import_metadata("test-repo-v4", _sample_tables())
    columns = repo.get_columns("dwd_order_di")
    by_name = {c["name"]: c for c in columns}
    assert by_name["order_no"]["comment"] == "order number"


def test_count_tables():
    before = repo.count_tables()
    unique_table = [
        TableMeta(
            catalog="default",
            schema="default",
            table_name="unique_count_test_table",
            comment="count test",
            columns=[],
        ),
    ]
    repo.import_metadata("test-repo-v5", unique_table)
    after = repo.count_tables()
    assert after == before + 1
