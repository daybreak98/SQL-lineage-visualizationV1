from fastapi import APIRouter, Query

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
