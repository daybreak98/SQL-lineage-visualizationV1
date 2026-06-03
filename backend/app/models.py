from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ─── 请求体 ────────────────────────────────────────────────────────

class AnalysisOptions(BaseModel):
    include_graph: bool = True
    include_semantics: bool = False
    include_diagnostics: bool = True
    include_source_location: bool = True
    include_expression_lineage: bool = False


class AnalyzeRequest(BaseModel):
    sql: str
    dialect: str = "spark"
    analysis_level: str = "column"
    default_catalog: str = "default"
    default_schema: str = "default"
    metadata_version: str = "latest"
    case_sensitive: bool = False
    analysis_options: AnalysisOptions = Field(default_factory=AnalysisOptions)


# ─── 响应体的各个零件 ──────────────────────────────────────────────

class Diagnostic(BaseModel):
    code: str
    level: str = "info"  # info | warning | error
    message: str


class DiagnosticsReport(BaseModel):
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0


class GraphViewModel(BaseModel):
    view_mode: str = "column"
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class OutputField(BaseModel):
    name: str
    display_name: str
    expression: str
    source_type: str = "unknown"  # unknown | expression | column


class StageStatus(BaseModel):
    stage: str
    status: str = "success"
    elapsed_ms: int = 0
    diagnostic_codes: list[str] = Field(default_factory=list)
    message: str | None = None


# ─── 主响应体 ──────────────────────────────────────────────────────

class AnalysisResult(BaseModel):
    schema_version: str = "0.3.0-c05"
    analysis_id: str = "analysis:c05"
    status: str = "partial"
    confidence_level: str = "unknown"
    confidence_reasons: list[str] = Field(default_factory=list)
    elapsed_ms: int = 0
    dialect: str = "spark"
    normalized_sql: str | None = None
    stage_statuses: list[StageStatus] = Field(default_factory=list)
    unsupported_features: list[str] = Field(default_factory=list)
    diagnostics_report: DiagnosticsReport = Field(default_factory=DiagnosticsReport)
    graph_view_model: GraphViewModel = Field(default_factory=GraphViewModel)
    output_fields: list[OutputField] = Field(default_factory=list)
    source_locations: dict[str, Any] = Field(default_factory=dict)
    metadata_context: dict[str, Any] = Field(default_factory=dict)
    semantics_report: Any = None
    summary: dict[str, Any] = Field(default_factory=dict)


# ─── 元数据导入 ──────────────────────────────────────────────────────

class MetadataImportRequest(BaseModel):
    mode: str  # preview | commit
    payload: dict[str, Any]


class ImportChangeItem(BaseModel):
    change_type: str
    object_type: str
    object_ref: dict[str, str | None]
    message: str | None = None


class MetadataImportResponse(BaseModel):
    status: str  # preview_ready | committed | failed
    import_batch_id: str | None = None
    metadata_version: str
    changes: list[ImportChangeItem] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


class MetadataTablesResponse(BaseModel):
    tables: list[dict[str, object]] = Field(default_factory=list)
    total: int = 0


class MetadataColumnsResponse(BaseModel):
    columns: list[dict[str, object]] = Field(default_factory=list)
    total: int = 0
