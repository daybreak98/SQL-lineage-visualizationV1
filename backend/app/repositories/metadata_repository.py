from __future__ import annotations

import sqlite3
from typing import Sequence

from app.db.sqlite import get_connection
from app.domain.metadata_model import ColumnMeta, TableMeta


def version_exists(metadata_version: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM metadata_imports WHERE metadata_version = ? LIMIT 1",
            (metadata_version,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def import_metadata(
    metadata_version: str,
    tables: Sequence[TableMeta],
    source_name: str | None = None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO metadata_imports (metadata_version, source_name, table_count, column_count) "
            "VALUES (?, ?, ?, ?)",
            (metadata_version, source_name, len(tables),
             sum(len(t.columns or []) for t in tables)),
        )
        import_id = cursor.lastrowid

        for table in tables:
            conn.execute("DELETE FROM column_metadata WHERE table_id IN "
                         "(SELECT id FROM table_metadata WHERE catalog=? AND schema_name=? AND table_name=?)",
                         (table.catalog, table.schema, table.table_name))
            conn.execute(
                "INSERT OR REPLACE INTO table_metadata (catalog, schema_name, table_name, comment, table_type, import_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (table.catalog, table.schema, table.table_name,
                 table.comment, table.table_type, import_id),
            )
            table_id_row = conn.execute(
                "SELECT id FROM table_metadata WHERE catalog=? AND schema_name=? AND table_name=?",
                (table.catalog, table.schema, table.table_name),
            ).fetchone()
            table_id = table_id_row["id"]

            for col in table.columns or []:
                conn.execute(
                    "INSERT OR REPLACE INTO column_metadata (table_id, name, data_type, comment, ordinal, "
                    "is_partition, nullable) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (table_id, col.name, col.data_type, col.comment,
                     col.ordinal, int(col.is_partition), int(col.nullable) if col.nullable is not None else None),
                )

        conn.commit()
        return import_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_tables() -> list[dict[str, object]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT catalog, schema_name, table_name, comment, table_type FROM table_metadata ORDER BY table_name"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_columns(table_name: str) -> list[dict[str, object]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT cm.name, cm.data_type, cm.comment, cm.ordinal, cm.is_partition, cm.nullable "
            "FROM column_metadata cm "
            "JOIN table_metadata tm ON cm.table_id = tm.id "
            "WHERE tm.table_name = ? "
            "ORDER BY cm.ordinal, cm.name",
            (table_name,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_columns_for_tables(table_names: list[str]) -> dict[str, list[dict[str, object]]]:
    if not table_names:
        return {}
    placeholders = ",".join("?" for _ in table_names)
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT tm.table_name, cm.name, cm.data_type, cm.comment "
            f"FROM column_metadata cm "
            f"JOIN table_metadata tm ON cm.table_id = tm.id "
            f"WHERE tm.table_name IN ({placeholders}) "
            f"ORDER BY tm.table_name, cm.ordinal, cm.name",
            table_names,
        ).fetchall()
        result: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            tname = row["table_name"]
            if tname not in result:
                result[tname] = []
            result[tname].append(dict(row))
        return result
    finally:
        conn.close()


def count_tables() -> int:
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM table_metadata").fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()
