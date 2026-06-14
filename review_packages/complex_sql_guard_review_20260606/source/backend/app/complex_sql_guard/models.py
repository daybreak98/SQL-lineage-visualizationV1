from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AnalysisStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ParseStatus(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class SourceLocation:
    start_offset: int
    end_offset: int
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Diagnostic:
    code: str
    severity: Severity
    message: str
    stage: str
    location: SourceLocation | None = None
    confidence: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "stage": self.stage,
            "confidence": self.confidence,
            "extra": self.extra,
        }
        if self.location is not None:
            payload["location"] = self.location.to_dict()
        return payload


@dataclass
class Placeholder:
    placeholder: str
    kind: str
    raw_text: str
    location: SourceLocation

    def to_dict(self) -> dict[str, Any]:
        return {
            "placeholder": self.placeholder,
            "kind": self.kind,
            "raw_text": self.raw_text,
            **self.location.to_dict(),
        }


@dataclass
class OffsetMapping:
    original_length: int
    normalized_to_original: list[int] = field(default_factory=list)
    analysis_to_original: list[int] = field(default_factory=list)

    def original_offset_for_normalized(self, offset: int) -> int:
        if not self.normalized_to_original:
            return max(0, min(offset, self.original_length))
        if offset <= 0:
            return 0
        if offset >= len(self.normalized_to_original):
            return self.original_length
        return self.normalized_to_original[offset]

    def original_offset_for_analysis(self, offset: int) -> int:
        if not self.analysis_to_original:
            return max(0, min(offset, self.original_length))
        if offset <= 0:
            return 0
        if offset >= len(self.analysis_to_original):
            return self.original_length
        return self.analysis_to_original[offset]

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_length": self.original_length,
            "has_normalized_mapping": bool(self.normalized_to_original),
            "has_analysis_mapping": bool(self.analysis_to_original),
            "normalized_length": len(self.normalized_to_original),
            "analysis_length": len(self.analysis_to_original),
        }


@dataclass
class SqlTextBundle:
    original_sql: str
    normalized_sql: str
    analysis_sql: str
    placeholders: list[Placeholder] = field(default_factory=list)
    offset_mapping: OffsetMapping | None = None

    def placeholder_lookup(self) -> dict[str, str]:
        return {placeholder.placeholder: placeholder.raw_text for placeholder in self.placeholders}

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_sql": self.original_sql,
            "normalized_sql": self.normalized_sql,
            "analysis_sql": self.analysis_sql,
            "has_normalized_sql": bool(self.normalized_sql),
            "has_analysis_sql": bool(self.analysis_sql),
            "placeholder_count": len(self.placeholders),
            "placeholders": [placeholder.to_dict() for placeholder in self.placeholders],
            "offset_mapping": self.offset_mapping.to_dict() if self.offset_mapping else {},
        }


@dataclass
class PreflightReport:
    char_count: int
    line_count: int
    max_parentheses_depth: int
    quote_balance_ok: bool
    contains_templates: bool = False
    contains_lateral_view: bool = False
    contains_regex_functions: bool = False
    contains_json_functions: bool = False
    contains_invisible_characters: bool = False
    complexity_score: int = 0
    risk_flags: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "char_count": self.char_count,
            "line_count": self.line_count,
            "max_parentheses_depth": self.max_parentheses_depth,
            "quote_balance_ok": self.quote_balance_ok,
            "contains_templates": self.contains_templates,
            "contains_lateral_view": self.contains_lateral_view,
            "contains_regex_functions": self.contains_regex_functions,
            "contains_json_functions": self.contains_json_functions,
            "contains_invisible_characters": self.contains_invisible_characters,
            "complexity_score": self.complexity_score,
            "risk_flags": self.risk_flags,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


@dataclass
class SqlSegment:
    segment_id: str
    segment_type: str
    raw_text: str
    start_offset: int
    end_offset: int
    parent_segment_id: str | None = None
    parse_status: ParseStatus = ParseStatus.NOT_ATTEMPTED
    diagnostics: list[Diagnostic] = field(default_factory=list)
    location: SourceLocation | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "segment_id": self.segment_id,
            "segment_type": self.segment_type,
            "raw_text": self.raw_text,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "parent_segment_id": self.parent_segment_id,
            "parse_status": self.parse_status.value,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }
        if self.location is not None:
            payload["location"] = self.location.to_dict()
        return payload


@dataclass
class ParseStageStatus:
    stage: str
    status: str
    elapsed_ms: int
    diagnostic_codes: list[str] = field(default_factory=list)
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParseAttempt:
    target: str
    dialect: str
    status: ParseStatus
    elapsed_ms: int = 0
    error_message: str | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    tree: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "dialect": self.dialect,
            "status": self.status.value,
            "elapsed_ms": self.elapsed_ms,
            "error_message": self.error_message,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


@dataclass
class ComplexSqlAnalysisResult:
    status: AnalysisStatus
    dialect: str
    text_bundle: SqlTextBundle
    preflight_report: PreflightReport
    segments: list[SqlSegment]
    parse_attempts: list[ParseAttempt]
    diagnostics: list[Diagnostic]
    stage_statuses: list[ParseStageStatus]
    capabilities: dict[str, Any]
    confidence: dict[str, float]
    unsupported_features: list[str] = field(default_factory=list)
    selected_target: str | None = None
    selected_tree: Any | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "dialect": self.dialect,
            "text_bundle": self.text_bundle.to_dict(),
            "preflight_report": self.preflight_report.to_dict(),
            "segments": [segment.to_dict() for segment in self.segments],
            "parse_attempts": [attempt.to_dict() for attempt in self.parse_attempts],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "stage_statuses": [stage.to_dict() for stage in self.stage_statuses],
            "unsupported_features": self.unsupported_features,
            "capabilities": self.capabilities,
            "confidence": self.confidence,
            "selected_target": self.selected_target,
        }

