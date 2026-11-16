import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel

from app.db.sqlite import DB_PATH
from app.models import (
    MetadataColumnsResponse,
    MetadataImportRequest,
    MetadataImportResponse,
    MetadataTablesResponse,
)
from app.repositories import metadata_repository as repo
from app.services.metadata_import_service import preview, commit

router = APIRouter()


@router.post("/metadata/import/preview", response_model=MetadataImportResponse)
async def import_preview(request: MetadataImportRequest) -> MetadataImportResponse:
    result = preview(request.payload)
    return MetadataImportResponse(
        status=result.status,
        import_batch_id=result.import_batch_id,
        metadata_version=result.metadata_version,
        changes=[dict(c.__dict__) for c in result.changes],
        diagnostics=result.diagnostics,
        summary=result.summary,
    )


@router.post("/metadata/import/commit", response_model=MetadataImportResponse)
async def import_commit(request: MetadataImportRequest) -> MetadataImportResponse:
    result = commit(request.payload)
    return MetadataImportResponse(
        status=result.status,
        import_batch_id=result.import_batch_id,
        metadata_version=result.metadata_version,
        changes=[dict(c.__dict__) for c in result.changes],
        diagnostics=result.diagnostics,
        summary=result.summary,
    )


@router.get("/metadata/tables", response_model=MetadataTablesResponse)
async def list_tables() -> MetadataTablesResponse:
    tables = repo.list_tables()
    return MetadataTablesResponse(tables=tables, total=len(tables))


@router.get("/metadata/columns", response_model=MetadataColumnsResponse)
async def list_columns(table_name: str = Query("")) -> MetadataColumnsResponse:
    if not table_name:
        return MetadataColumnsResponse(columns=[], total=0)
    columns = repo.get_columns(table_name)
    return MetadataColumnsResponse(columns=columns, total=len(columns))


class MetadataUploadResponse(BaseModel):
    status: str  # success | failed
    message: str | None = None
    table_count: int = 0
    column_count: int = 0


# Minimum column layout of the workbench metadata migration. Uploads may
# contain additional columns or tables.
_REQUIRED_COLUMNS = {
    "metadata_imports": {"id", "metadata_version", "source_name", "imported_at", "table_count", "column_count"},
    "table_metadata": {"id", "catalog", "schema_name", "table_name", "comment", "table_type", "import_id"},
    "column_metadata": {"id", "table_id", "name", "data_type", "comment", "ordinal", "is_partition", "nullable"},
}


def _validate_metadata_db(db_path: Path) -> tuple[bool, str, int, int]:
    """Check the staged upload's required tables and columns before touching the live DB."""
    try:
        conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {row[0] for row in rows}
            missing = _REQUIRED_COLUMNS.keys() - table_names
            if missing:
                return False, f"Missing required tables: {', '.join(sorted(missing))}", 0, 0
            missing_columns = []
            for table, required in _REQUIRED_COLUMNS.items():
                columns = {row[0].lower() for row in conn.execute(
                    "SELECT name FROM pragma_table_info(?)", (table,)
                )}
                missing_columns.extend(f"{table}.{name}" for name in sorted(required - columns))
            if missing_columns:
                return False, f"Missing required columns: {', '.join(missing_columns)}", 0, 0
            table_count = conn.execute("SELECT COUNT(*) FROM table_metadata").fetchone()[0]
            column_count = conn.execute("SELECT COUNT(*) FROM column_metadata").fetchone()[0]
            return True, "ok", table_count, column_count
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return False, f"Not a valid SQLite file: {exc}", 0, 0


@router.post("/metadata/upload-db", response_model=MetadataUploadResponse)
async def upload_metadata_db(file: UploadFile = File(...)) -> MetadataUploadResponse:
    tmp_path = Path(tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)
    try:
        with open(tmp_path, "wb") as out:
            shutil.copyfileobj(file.file, out)

        ok, message, table_count, column_count = _validate_metadata_db(tmp_path)
        if not ok:
            return MetadataUploadResponse(status="failed", message=message)

        # Use SQLite online backup API to copy uploaded db content into the
        # live db in-place. This avoids any file replacement / lock issues on
        # Windows (the backend process holds the live db file open).
        if DB_PATH.exists():
            backup = DB_PATH.with_suffix(".db.bak")
            live_conn = sqlite3.connect(str(DB_PATH))
            try:
                bak_conn = sqlite3.connect(str(backup))
                try:
                    live_conn.backup(bak_conn)
                finally:
                    bak_conn.close()
            finally:
                live_conn.close()

        live_conn = sqlite3.connect(str(DB_PATH))
        src_conn = sqlite3.connect(str(tmp_path))
        try:
            src_conn.backup(live_conn)
        finally:
            live_conn.close()
            src_conn.close()

        return MetadataUploadResponse(
            status="success",
            message="Metadata database replaced.",
            table_count=table_count,
            column_count=column_count,
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
