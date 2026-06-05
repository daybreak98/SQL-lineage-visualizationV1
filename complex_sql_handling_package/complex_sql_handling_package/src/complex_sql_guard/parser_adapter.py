from __future__ import annotations

from typing import Optional

from .models import Diagnostic, ParseAttempt, ParseStatus, Severity


class ParserAdapter:
    def parse(self, sql: str, dialect: str, target: str) -> ParseAttempt:
        raise NotImplementedError


class SqlglotParserAdapter(ParserAdapter):
    """Thin adapter around sqlglot.

    Keep sqlglot dependency isolated so domain services do not depend on
    sqlglot AST directly. This also lets the project run without sqlglot in
    environments where only preprocessing tests are needed.
    """

    def parse(self, sql: str, dialect: str, target: str) -> ParseAttempt:
        try:
            import sqlglot  # type: ignore
        except Exception as exc:
            return ParseAttempt(
                target=target,
                dialect=dialect,
                status=ParseStatus.FAILED,
                error_message="sqlglot is not installed",
                diagnostics=[Diagnostic(
                    code="SQLGLOT_NOT_INSTALLED",
                    severity=Severity.WARNING,
                    message="sqlglot is not installed; parser stage is skipped but preprocessing/segmenting still works.",
                    stage="parse",
                    confidence=1.0,
                    extra={"exception": repr(exc)},
                )],
            )

        try:
            # parse, not parse_one, to support multiple statements defensively.
            sqlglot.parse(sql, read=dialect)
            return ParseAttempt(target=target, dialect=dialect, status=ParseStatus.SUCCESS)
        except Exception as exc:
            return ParseAttempt(
                target=target,
                dialect=dialect,
                status=ParseStatus.FAILED,
                error_message=str(exc),
                diagnostics=[Diagnostic(
                    code="PARSE_ERROR",
                    severity=Severity.WARNING,
                    message=f"Parser failed on {target}: {exc}",
                    stage="parse",
                    confidence=0.5,
                )],
            )
