from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.metadata_model import ColumnMeta, TableMeta
from app.models import Diagnostic
from app.repositories import metadata_repository as repo


@dataclass(frozen=True)
class ImportChange:
    change_type: str  # added | unchanged | conflict
    object_type: str  # table | column
    object_ref: dict[str, str | None]
    message: str | None = None


@dataclass
class MetadataImportResult:
    status: str  # preview_ready | committed | failed
    import_batch_id: str | None
    metadata_version: str
    changes: list[ImportChange] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)


def preview(payload: dict) -> MetadataImportResult:
    tables = _parse_tables(payload)
    changes = _build_changes(tables, "added")
    return MetadataImportResult(
        status="preview_ready",
        import_batch_id=None,
        metadata_version=payload.get("metadata_version", "unknown"),
        changes=changes,
        summary={
            "table_count": len(tables),
            "column_count": sum(len(t.columns or []) for t in tables),
        },
    )


def commit(payload: dict) -> MetadataImportResult:
    metadata_version = payload.get("metadata_version", "unknown")

    if repo.version_exists(metadata_version):
        tables = _parse_tables(payload)
        return MetadataImportResult(
            status="committed",
            import_batch_id=None,
            metadata_version=metadata_version,
            changes=_build_changes(tables, "unchanged"),
            diagnostics=[
                Diagnostic(
                    code="METADATA_VERSION_EXISTS",
                    level="info",
                    message=f"Metadata version {metadata_version} already exists, skipped import.",
                )
            ],
            summary={
                "table_count": len(tables),
                "column_count": sum(len(t.columns or []) for t in tables),
            },
        )

    tables = _parse_tables(payload)
    import_id = repo.import_metadata(
        metadata_version=metadata_version,
        tables=tables,
        source_name=payload.get("source_name"),
    )
    return MetadataImportResult(
        status="committed",
        import_batch_id=str(import_id),
        metadata_version=metadata_version,
        changes=_build_changes(tables, "added"),
        summary={
            "table_count": len(tables),
            "column_count": sum(len(t.columns or []) for t in tables),
        },
    )


def _parse_tables(payload: dict) -> list[TableMeta]:
    tables: list[TableMeta] = []
    for t in payload.get("tables", []):
        columns = [
            ColumnMeta(
                name=c["name"],
                data_type=c.get("data_type", ""),
                comment=c.get("comment", ""),
                ordinal=c.get("ordinal"),
                is_partition=c.get("is_partition", False),
                nullable=c.get("nullable", True),
            )
            for c in t.get("columns", [])
        ]
        tables.append(
            TableMeta(
                catalog=t.get("catalog", payload.get("default_catalog", "default")),
                schema=t.get("schema", payload.get("default_schema", "default")),
                table_name=t.get("table_name", t.get("name", "")),
                comment=t.get("comment", ""),
                table_type=t.get("table_type", "table"),
                columns=columns,
            )
        )
    return tables


def _build_changes(tables: list[TableMeta], change_type: str) -> list[ImportChange]:
    changes: list[ImportChange] = []
    for table in tables:
        changes.append(
            ImportChange(
                change_type=change_type,
                object_type="table",
                object_ref={
                    "catalog": table.catalog,
                    "schema": table.schema,
                    "table": table.table_name,
                    "column": None,
                },
            )
        )
        for col in table.columns or []:
            changes.append(
                ImportChange(
                    change_type=change_type,
                    object_type="column",
                    object_ref={
                        "catalog": table.catalog,
                        "schema": table.schema,
                        "table": table.table_name,
                        "column": col.name,
                    },
                )
            )
    return changes
