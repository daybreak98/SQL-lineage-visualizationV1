from __future__ import annotations

import time

from . import diagnostics as diag_codes
from .models import Diagnostic, ParseAttempt, ParseStatus, Severity


class ParserAdapter:
    def parse(self, sql: str, dialect: str, target: str) -> ParseAttempt:
        raise NotImplementedError


class SqlglotParserAdapter(ParserAdapter):
    def parse(self, sql: str, dialect: str, target: str) -> ParseAttempt:
        started = time.perf_counter()
        try:
            import sqlglot
        except Exception as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            return ParseAttempt(
                target=target,
                dialect=dialect,
                status=ParseStatus.FAILED,
                elapsed_ms=elapsed,
                error_message="sqlglot is not installed",
                diagnostics=[Diagnostic(
                    code=diag_codes.SQLGLOT_NOT_INSTALLED,
                    severity=Severity.WARNING,
                    message="sqlglot is not installed; parser stage is skipped.",
                    stage="sql_parse",
                    confidence=1.0,
                    extra={"exception": repr(exc)},
                )],
            )

        try:
            tree = sqlglot.parse_one(sql, dialect=dialect)
            elapsed = int((time.perf_counter() - started) * 1000)
            return ParseAttempt(
                target=target,
                dialect=dialect,
                status=ParseStatus.SUCCESS,
                elapsed_ms=elapsed,
                tree=tree,
            )
        except Exception as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            return ParseAttempt(
                target=target,
                dialect=dialect,
                status=ParseStatus.FAILED,
                elapsed_ms=elapsed,
                error_message=str(exc),
                diagnostics=[Diagnostic(
                    code=diag_codes.SQLGLOT_PARSE_ERROR,
                    severity=Severity.WARNING,
                    message=f"sqlglot failed on {target}: {exc}",
                    stage="sql_parse",
                    confidence=0.4,
                    extra={"target": target},
                )],
            )

