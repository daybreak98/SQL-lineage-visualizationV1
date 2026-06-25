from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.db.sqlite import DB_PATH

client = TestClient(app)


def _make_valid_metadata_db(tmp_path: Path) -> Path:
    """Create a sqlite db with the 3 required tables + sample data."""
    db_path = tmp_path / "valid.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE metadata_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metadata_version TEXT NOT NULL,
            source_name TEXT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            table_count INTEGER DEFAULT 0,
            column_count INTEGER DEFAULT 0
        );
        CREATE TABLE table_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            catalog TEXT DEFAULT 'default',
            schema_name TEXT DEFAULT 'default',
            table_name TEXT NOT NULL,
            comment TEXT,
            table_type TEXT DEFAULT 'table',
            import_id INTEGER,
            UNIQUE(catalog, schema_name, table_name)
        );
        CREATE TABLE column_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            data_type TEXT,
            comment TEXT,
            ordinal INTEGER,
            is_partition BOOLEAN DEFAULT 0,
            nullable BOOLEAN DEFAULT 1,
            UNIQUE(table_id, name)
        );
        INSERT INTO metadata_imports (metadata_version, table_count, column_count)
            VALUES ('upload-test', 1, 2);
        INSERT INTO table_metadata (id, catalog, schema_name, table_name, comment, import_id)
            VALUES (1, 'default', 'default', 'upload_table', 'from upload', 1);
        INSERT INTO column_metadata (table_id, name, data_type, comment, ordinal)
            VALUES (1, 'col_a', 'string', 'a', 1), (1, 'col_b', 'int', 'b', 2);
    """)
    conn.commit()
    conn.close()
    return db_path


def test_upload_valid_db_returns_success(tmp_path, monkeypatch):
    # Redirect DB_PATH to tmp_path so we don't clobber the real metadata.db
    real_db = tmp_path / "metadata.db"
    monkeypatch.setattr("app.db.sqlite.DB_PATH", real_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", real_db)

    valid_db = _make_valid_metadata_db(tmp_path)

    with open(valid_db, "rb") as f:
        resp = client.post(
            "/api/metadata/upload-db",
            files={"file": ("valid.db", f, "application/octet-stream")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["table_count"] == 1
    assert data["column_count"] == 2
    assert real_db.exists()


def test_upload_non_sqlite_file_returns_failed(tmp_path, monkeypatch):
    real_db = tmp_path / "metadata.db"
    monkeypatch.setattr("app.db.sqlite.DB_PATH", real_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", real_db)

    bad_file = tmp_path / "fake.db"
    bad_file.write_text("this is not a sqlite file")

    with open(bad_file, "rb") as f:
        resp = client.post(
            "/api/metadata/upload-db",
            files={"file": ("fake.db", f, "application/octet-stream")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert "valid SQLite" in data["message"] or "file is not a database" in data["message"]
    assert not real_db.exists()


def test_upload_db_missing_tables_returns_failed(tmp_path, monkeypatch):
    real_db = tmp_path / "metadata.db"
    monkeypatch.setattr("app.db.sqlite.DB_PATH", real_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", real_db)

    incomplete_db = tmp_path / "incomplete.db"
    conn = sqlite3.connect(str(incomplete_db))
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()

    with open(incomplete_db, "rb") as f:
        resp = client.post(
            "/api/metadata/upload-db",
            files={"file": ("incomplete.db", f, "application/octet-stream")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert "table_metadata" in data["message"]
    assert not real_db.exists()


def test_upload_backs_up_old_db(tmp_path, monkeypatch):
    real_db = tmp_path / "metadata.db"
    # Pre-create an "old" db so we can verify backup
    old_conn = sqlite3.connect(str(real_db))
    old_conn.execute("CREATE TABLE table_metadata (id INTEGER)")
    old_conn.execute("CREATE TABLE column_metadata (id INTEGER)")
    old_conn.execute("CREATE TABLE metadata_imports (id INTEGER)")
    old_conn.execute("INSERT INTO table_metadata VALUES (99)")
    old_conn.commit()
    old_conn.close()

    monkeypatch.setattr("app.db.sqlite.DB_PATH", real_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", real_db)

    valid_db = _make_valid_metadata_db(tmp_path)
    with open(valid_db, "rb") as f:
        resp = client.post(
            "/api/metadata/upload-db",
            files={"file": ("valid.db", f, "application/octet-stream")},
        )

    assert resp.status_code == 200
    backup = real_db.with_suffix(".db.bak")
    assert backup.exists()
    # Backup should contain the old row
    bak_conn = sqlite3.connect(str(backup))
    rows = bak_conn.execute("SELECT id FROM table_metadata").fetchall()
    bak_conn.close()
    assert (99,) in rows


def test_upload_large_db_not_rejected_by_body_limit(tmp_path, monkeypatch):
    real_db = tmp_path / "metadata.db"
    monkeypatch.setattr("app.db.sqlite.DB_PATH", real_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", real_db)

    valid_db = _make_valid_metadata_db(tmp_path)
    # Pad the db file to > 2MB to exceed MAX_REQUEST_BODY_BYTES
    with open(valid_db, "ab") as f:
        f.write(b"\0" * (3 * 1024 * 1024))

    with open(valid_db, "rb") as f:
        resp = client.post(
            "/api/metadata/upload-db",
            files={"file": ("big.db", f, "application/octet-stream")},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
