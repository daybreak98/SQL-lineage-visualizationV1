from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlglot.expressions import Expression

from app.adapters.sqlglot_adapter import extract_output_fields_from_tree
from app.complex_sql_guard import analyze_complex_sql
from app.domain import diagnostics_model as diag_codes
from app.models import Diagnostic, OutputField


@dataclass
class ParseServiceResult:
    success: bool
    status: str
    output_fields: list[OutputField]
    diagnostics: list[Diagnostic]
    elapsed_ms: int
    dialect: str
    stage_statuses: list[dict[str, object]]
    tree: Expression | None = None
    normalized_sql: str | None = None
    analysis_sql: str | None = None
    sql_text_bundle: dict[str, object] = field(default_factory=dict)
    preflight_report: dict[str, object] = field(default_factory=dict)
    segments: list[dict[str, object]] = field(default_factory=list)
    parse_attempts: list[dict[str, object]] = field(default_factory=list)
    capabilities: dict[str, object] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    unsupported_features: list[str] = field(default_factory=list)
    selected_target: str | None = None


def parse_sql(
    sql: str,
    dialect: str = "spark",
    options: dict[str, object] | None = None,
) -> ParseServiceResult:
    started = time.time()
    complex_result = analyze_complex_sql(sql, dialect=dialect, options=options or {})

    tree = complex_result.selected_tree
    output_fields = (
        [
            OutputField(**payload)
            for payload in extract_output_fields_from_tree(
                tree,
                dialect=dialect,
                placeholder_map=complex_result.text_bundle.placeholder_lookup(),
            )
        ]
        if tree is not None
        else []
    )

    diagnostics = [_to_api_diagnostic(diagnostic) for diagnostic in complex_result.diagnostics]
    diagnostics = _append_compat_parse_error(
        diagnostics,
        status=complex_result.status.value,
        hard_failure=tree is None,
    )
    diagnostics = _compatibility_filter_diagnostics(complex_result.status.value, diagnostics)
    diagnostics = _dedupe_diagnostics(diagnostics)

    elapsed_ms = int((time.time() - started) * 1000)
    stage_statuses = [stage.to_dict() for stage in complex_result.stage_statuses]
    stage_statuses = _reorder_stage_statuses(stage_statuses)
    stage_statuses = _compatibility_filter_stage_statuses(complex_result.status.value, diagnostics, stage_statuses)
    return ParseServiceResult(
        success=tree is not None,
        status=complex_result.status.value,
        output_fields=output_fields,
        diagnostics=diagnostics,
        elapsed_ms=elapsed_ms,
        dialect=dialect,
        stage_statuses=stage_statuses,
        tree=tree,
        normalized_sql=complex_result.text_bundle.normalized_sql,
        analysis_sql=complex_result.text_bundle.analysis_sql,
        sql_text_bundle=complex_result.text_bundle.to_dict(),
        preflight_report=complex_result.preflight_report.to_dict(),
        segments=[segment.to_dict() for segment in complex_result.segments],
        parse_attempts=[attempt.to_dict() for attempt in complex_result.parse_attempts],
        capabilities=complex_result.capabilities,
        confidence=complex_result.confidence,
        unsupported_features=complex_result.unsupported_features,
        selected_target=complex_result.selected_target,
    )


def _to_api_diagnostic(complex_diagnostic) -> Diagnostic:
    severity = complex_diagnostic.severity.value
    return Diagnostic(
        code=complex_diagnostic.code,
        level=severity,
        severity=severity,
        message=complex_diagnostic.message,
        stage=complex_diagnostic.stage,
        location=complex_diagnostic.location.to_dict() if complex_diagnostic.location is not None else None,
        confidence=complex_diagnostic.confidence,
        extra=complex_diagnostic.extra,
    )


def _append_compat_parse_error(
    diagnostics: list[Diagnostic],
    *,
    status: str,
    hard_failure: bool,
) -> list[Diagnostic]:
    parse_errors = [diagnostic for diagnostic in diagnostics if diagnostic.code == diag_codes.SQLGLOT_PARSE_ERROR]
    if not parse_errors:
        return diagnostics
    if any(diagnostic.code == diag_codes.SQL_PARSE_ERROR for diagnostic in diagnostics):
        return diagnostics
    if status == "success" and not hard_failure:
        return diagnostics

    diagnostics.append(Diagnostic(
        code=diag_codes.SQL_PARSE_ERROR,
        level="error" if hard_failure else "warning",
        severity="error" if hard_failure else "warning",
        message=parse_errors[0].message,
        stage="sql_parse",
        confidence=parse_errors[0].confidence,
    ))
    return diagnostics


def _dedupe_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    seen: set[tuple[str, str | None, str]] = set()
    result: list[Diagnostic] = []
    for diagnostic in diagnostics:
        key = (diagnostic.code, diagnostic.stage, diagnostic.message)
        if key in seen:
            continue
        seen.add(key)
        result.append(diagnostic)
    return result


def _compatibility_filter_diagnostics(status: str, diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    if status != "failed":
        return diagnostics
    parse_error = next((diagnostic for diagnostic in diagnostics if diagnostic.code == diag_codes.SQL_PARSE_ERROR), None)
    if parse_error is not None:
        return [parse_error]
    return diagnostics[:1]


def _reorder_stage_statuses(stage_statuses: list[dict[str, object]]) -> list[dict[str, object]]:
    sql_parse = [stage for stage in stage_statuses if stage.get("stage") == "sql_parse"]
    others = [stage for stage in stage_statuses if stage.get("stage") != "sql_parse"]
    return sql_parse + others


def _compatibility_filter_stage_statuses(
    status: str,
    diagnostics: list[Diagnostic],
    stage_statuses: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not stage_statuses:
        return stage_statuses

    first = dict(stage_statuses[0])
    if first.get("stage") == "sql_parse":
        if status == "failed":
            first["status"] = "failed"
            first["diagnostic_codes"] = [diag_codes.SQL_PARSE_ERROR]
            parse_error = next((diagnostic for diagnostic in diagnostics if diagnostic.code == diag_codes.SQL_PARSE_ERROR), None)
            first["message"] = parse_error.message if parse_error is not None else first.get("message")
        elif status == "success":
            first["status"] = "success"
    return [first] + stage_statuses[1:]
