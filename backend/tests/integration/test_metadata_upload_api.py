from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.db.sqlite import DB_PATH

client = TestClient(app)


def _make_valid_metadata_db(tmp_path: Path, *, unique_table_identity: bool = True) -> Path:
    """Create a sqlite db with the 3 required tables + sample data."""
    db_path = tmp_path / "valid.db"
    conn = sqlite3.connect(str(db_path))
    table_identity = ", UNIQUE(catalog, schema_name, table_name)" if unique_table_identity else ""
    conn.executescript(f"""
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
            import_id INTEGER{table_identity}
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
    conn = sqlite3.connect(valid_db)
    try:
        conn.execute("ALTER TABLE table_metadata ADD COLUMN export_note TEXT")
    finally:
        conn.close()

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


def test_upload_db_missing_required_column_preserves_live_db(tmp_path, monkeypatch):
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    live_db = _make_valid_metadata_db(live_dir)
    original = live_db.read_bytes()
    monkeypatch.setattr("app.db.sqlite.DB_PATH", live_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", live_db)

    incomplete = _make_valid_metadata_db(tmp_path)
    conn = sqlite3.connect(incomplete)
    try:
        conn.execute("ALTER TABLE column_metadata DROP COLUMN ordinal")
    finally:
        conn.close()

    with incomplete.open("rb") as stream:
        resp = client.post(
            "/api/metadata/upload-db",
            files={"file": ("incomplete.db", stream, "application/octet-stream")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert (data["status"], live_db.read_bytes() == original) == ("failed", True)
    assert "column_metadata.ordinal" in data["message"]
    assert not live_db.with_suffix(".db.bak").exists()


def test_upload_db_without_unique_table_identity_preserves_queryable_live_db(tmp_path, monkeypatch):
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    live_db = _make_valid_metadata_db(live_dir)
    with sqlite3.connect(live_db) as conn:
        conn.execute("UPDATE table_metadata SET table_name = 'retained_table'")
    conn.close()
    original = live_db.read_bytes()
    monkeypatch.setattr("app.db.sqlite.DB_PATH", live_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", live_db)

    incompatible = _make_valid_metadata_db(tmp_path, unique_table_identity=False)
    with incompatible.open("rb") as stream:
        upload = client.post(
            "/api/metadata/upload-db",
            files={"file": ("missing-unique.db", stream, "application/octet-stream")},
        )
    tables = client.get("/api/metadata/tables")

    assert upload.status_code == tables.status_code == 200
    data = upload.json()
    names = [table["table_name"] for table in tables.json()["tables"]]
    assert (data["status"], live_db.read_bytes() == original, names) == ("failed", True, ["retained_table"])
    assert "table_metadata(catalog, schema_name, table_name)" in data["message"]
    assert not live_db.with_suffix(".db.bak").exists()


def test_upload_db_with_corrupt_import_history_preserves_live_db(tmp_path, monkeypatch):
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    live_db = _make_valid_metadata_db(live_dir)
    original = live_db.read_bytes()
    monkeypatch.setattr("app.db.sqlite.DB_PATH", live_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", live_db)

    corrupt = _make_valid_metadata_db(tmp_path)
    conn = sqlite3.connect(corrupt)
    try:
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        root_page = conn.execute(
            "SELECT rootpage FROM sqlite_schema WHERE name = 'metadata_imports'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert root_page > 1
    with corrupt.open("r+b") as stream:
        stream.seek((root_page - 1) * page_size)
        stream.write(b"\0")  # Invalid B-tree page type; leave sqlite_schema unchanged.

    with corrupt.open("rb") as stream:
        upload = client.post(
            "/api/metadata/upload-db",
            files={"file": ("corrupt-history.db", stream, "application/octet-stream")},
        )
    assert upload.status_code == 200
    data = upload.json()
    assert (data["status"], live_db.read_bytes() == original) == ("failed", True)
    assert "Unreadable metadata import history" in data["message"]
    assert not live_db.with_suffix(".db.bak").exists()
    assert client.get("/api/metadata/tables").json()["tables"][0]["table_name"] == "upload_table"


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


def test_upload_succeeds_while_live_db_held_open(tmp_path, monkeypatch):
    """Reproduce the production scenario: backend holds an open connection to
    the live metadata.db (e.g. from a concurrent list_tables request). File
    replacement would fail with WinError 5/32; the SQLite backup-API path
    must still succeed."""
    real_db = tmp_path / "metadata.db"
    # Seed the live db with the required schema + an old row
    setup = sqlite3.connect(str(real_db))
    setup.executescript("""
        CREATE TABLE metadata_imports (id INTEGER PRIMARY KEY, metadata_version TEXT, source_name TEXT, imported_at TIMESTAMP, table_count INTEGER, column_count INTEGER);
        CREATE TABLE table_metadata (id INTEGER PRIMARY KEY, catalog TEXT, schema_name TEXT, table_name TEXT, comment TEXT, table_type TEXT, import_id INTEGER);
        CREATE TABLE column_metadata (id INTEGER PRIMARY KEY, table_id INTEGER, name TEXT, data_type TEXT, comment TEXT, ordinal INTEGER, is_partition BOOLEAN, nullable BOOLEAN);
        INSERT INTO table_metadata VALUES (777, 'default', 'default', 'old_row', 'x', 'table', NULL);
    """)
    setup.commit()
    setup.close()

    monkeypatch.setattr("app.db.sqlite.DB_PATH", real_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", real_db)

    # Hold an open connection to the live db (simulates backend process)
    holder = sqlite3.connect(str(real_db))
    holder.execute("SELECT 1").fetchall()

    valid_db = _make_valid_metadata_db(tmp_path)
    with open(valid_db, "rb") as f:
        resp = client.post(
            "/api/metadata/upload-db",
            files={"file": ("valid.db", f, "application/octet-stream")},
        )

    holder.close()

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    # Live db content must now be the uploaded db's content, not the old row
    check = sqlite3.connect(str(real_db))
    rows = check.execute("SELECT table_name FROM table_metadata").fetchall()
    check.close()
    assert ("upload_table",) in rows
    assert ("old_row",) not in rows
