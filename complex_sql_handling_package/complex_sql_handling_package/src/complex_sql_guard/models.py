from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Diagnostic:
    code: str
    severity: Severity
    message: str
    stage: str
    location: Optional[SourceLocation] = None
    confidence: float = 1.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        if self.location:
            data["location"] = self.location.to_dict()
        return data


@dataclass
class Placeholder:
    placeholder: str
    kind: str
    raw_text: str
    location: SourceLocation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "placeholder": self.placeholder,
            "kind": self.kind,
            "raw_text": self.raw_text,
            "location": self.location.to_dict(),
        }


@dataclass
class SqlTextBundle:
    original_sql: str
    normalized_sql: str
    analysis_sql: str
    placeholders: List[Placeholder] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_sql": self.original_sql,
            "normalized_sql": self.normalized_sql,
            "analysis_sql": self.analysis_sql,
            "placeholders": [p.to_dict() for p in self.placeholders],
        }


@dataclass
class PreflightReport:
    char_count: int
    line_count: int
    max_parentheses_depth: int
    risk_flags: List[str] = field(default_factory=list)
    diagnostics: List[Diagnostic] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "char_count": self.char_count,
            "line_count": self.line_count,
            "max_parentheses_depth": self.max_parentheses_depth,
            "risk_flags": self.risk_flags,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


@dataclass
class SqlSegment:
    segment_id: str
    segment_type: str
    raw_text: str
    location: SourceLocation
    parse_status: ParseStatus = ParseStatus.NOT_ATTEMPTED
    diagnostics: List[Diagnostic] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "segment_type": self.segment_type,
            "raw_text": self.raw_text,
            "location": self.location.to_dict(),
            "parse_status": self.parse_status.value,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


@dataclass
class ParseAttempt:
    target: str
    dialect: str
    status: ParseStatus
    error_message: Optional[str] = None
    diagnostics: List[Diagnostic] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "dialect": self.dialect,
            "status": self.status.value,
            "error_message": self.error_message,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


@dataclass
class ComplexSqlAnalysisResult:
    status: AnalysisStatus
    dialect: str
    text_bundle: SqlTextBundle
    preflight_report: PreflightReport
    segments: List[SqlSegment]
    parse_attempts: List[ParseAttempt]
    diagnostics: List[Diagnostic]
    capabilities: Dict[str, Any]
    confidence: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "dialect": self.dialect,
            "text_bundle": self.text_bundle.to_dict(),
            "preflight_report": self.preflight_report.to_dict(),
            "segments": [s.to_dict() for s in self.segments],
            "parse_attempts": [p.to_dict() for p in self.parse_attempts],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "capabilities": self.capabilities,
            "confidence": self.confidence,
        }
