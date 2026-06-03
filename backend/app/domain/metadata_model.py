from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnMeta:
    name: str
    data_type: str = ""
    comment: str = ""
    ordinal: int | None = None
    is_partition: bool = False
    nullable: bool | None = True


@dataclass(frozen=True)
class TableMeta:
    catalog: str
    schema: str
    table_name: str
    comment: str = ""
    table_type: str = "table"
    columns: list[ColumnMeta] | None = None  # None = 未加载列


@dataclass(frozen=True)
class MetadataPayload:
    metadata_version: str
    tables: list[TableMeta]
    case_sensitive: bool = False
    default_catalog: str = "default"
    default_schema: str = "default"
    source_name: str | None = None
