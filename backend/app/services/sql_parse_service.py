from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlglot.expressions import Expression

from app.adapters.sqlglot_adapter import parse_and_extract
from app.models import Diagnostic, OutputField


@dataclass
class ParseServiceResult:
    success: bool
    status: str                     # success | failed
    output_fields: list[OutputField]
    diagnostics: list[Diagnostic]
    elapsed_ms: int
    dialect: str
    stage_statuses: list[dict[str, object]]
    tree: Expression | None = None


def parse_sql(sql: str, dialect: str = "spark") -> ParseServiceResult:
    started = time.time()

    result = parse_and_extract(sql, dialect)

    if result.success:
        elapsed = int((time.time() - started) * 1000)
        return ParseServiceResult(
            success=True,
            status="success",
            dialect=dialect,
            output_fields=[OutputField(**f) for f in result.output_fields],
            diagnostics=[],
            elapsed_ms=elapsed,
            tree=result.tree,
            stage_statuses=[
                {"stage": "sql_parse", "status": "success", "elapsed_ms": elapsed,
                 "diagnostic_codes": [], "message": "SQL parsed successfully."}
            ],
        )
    else:
        elapsed = int((time.time() - started) * 1000)
        return ParseServiceResult(
            success=False,
            status="failed",
            dialect=dialect,
            output_fields=[],
            diagnostics=[
                Diagnostic(
                    code="SQL_PARSE_ERROR",
                    level="error",
                    message=result.error_message or "Unknown SQL parse error.",
                )
            ],
            elapsed_ms=elapsed,
            stage_statuses=[
                {"stage": "sql_parse", "status": "failed", "elapsed_ms": elapsed,
                 "diagnostic_codes": ["SQL_PARSE_ERROR"], "message": result.error_message}
            ],
        )
