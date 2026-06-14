from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .models import Diagnostic, PreflightReport, Severity, SourceLocation


@dataclass
class PreflightOptions:
    max_sql_chars: int = 200_000
    warn_sql_chars: int = 50_000
    warn_line_count: int = 800


class PreflightChecker:
    """Cheap, non-destructive checks before parsing.

    This checker intentionally does not try to parse SQL. It only emits risk
    signals that downstream analyzer can expose to users.
    """

    def __init__(self, options: PreflightOptions | None = None) -> None:
        self.options = options or PreflightOptions()

    def check(self, sql: str) -> PreflightReport:
        diagnostics: List[Diagnostic] = []
        risk_flags: List[str] = []
        char_count = len(sql)
        line_count = sql.count("\n") + 1 if sql else 0
        max_depth, unbalanced = self._scan_parentheses(sql)

        if char_count > self.options.warn_sql_chars:
            risk_flags.append("LONG_SQL")
            diagnostics.append(Diagnostic(
                code="SQL_LONG_WARNING",
                severity=Severity.WARNING,
                message=f"SQL length is {char_count} chars; complex SQL handling will use defensive mode.",
                stage="preflight",
            ))

        if char_count > self.options.max_sql_chars:
            risk_flags.append("SQL_TOO_LONG")
            diagnostics.append(Diagnostic(
                code="SQL_TOO_LONG",
                severity=Severity.ERROR,
                message=f"SQL length {char_count} exceeds configured max {self.options.max_sql_chars}.",
                stage="preflight",
            ))

        if line_count > self.options.warn_line_count:
            risk_flags.append("MANY_LINES")
            diagnostics.append(Diagnostic(
                code="SQL_MANY_LINES",
                severity=Severity.WARNING,
                message=f"SQL has {line_count} lines; segment-level fallback is recommended.",
                stage="preflight",
            ))

        if unbalanced:
            risk_flags.append("UNBALANCED_PARENTHESES")
            diagnostics.append(Diagnostic(
                code="UNBALANCED_PARENTHESES",
                severity=Severity.WARNING,
                message="Parentheses appear to be unbalanced in a coarse scan.",
                stage="preflight",
            ))

        if "${" in sql or "#{" in sql or "<#" in sql:
            risk_flags.append("TEMPLATE_SQL_DETECTED")
            diagnostics.append(Diagnostic(
                code="TEMPLATE_SQL_DETECTED",
                severity=Severity.WARNING,
                message="Template variables or template blocks are detected.",
                stage="preflight",
            ))

        if "lateral view" in sql.lower() or "explode(" in sql.lower() or "posexplode(" in sql.lower():
            risk_flags.append("ROW_EXPANDING_FUNCTION_DETECTED")
            diagnostics.append(Diagnostic(
                code="ROW_EXPANDING_FUNCTION_DETECTED",
                severity=Severity.INFO,
                message="Row-expanding functions such as lateral view/explode are detected.",
                stage="preflight",
            ))

        return PreflightReport(
            char_count=char_count,
            line_count=line_count,
            max_parentheses_depth=max_depth,
            risk_flags=risk_flags,
            diagnostics=diagnostics,
        )

    def _scan_parentheses(self, sql: str) -> Tuple[int, bool]:
        depth = 0
        max_depth = 0
        in_single = False
        in_double = False
        in_backtick = False
        escaped = False
        unbalanced = False

        for ch in sql:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == "'" and not in_double and not in_backtick:
                in_single = not in_single
                continue
            if ch == '"' and not in_single and not in_backtick:
                in_double = not in_double
                continue
            if ch == "`" and not in_single and not in_double:
                in_backtick = not in_backtick
                continue
            if in_single or in_double or in_backtick:
                continue
            if ch == "(":
                depth += 1
                max_depth = max(max_depth, depth)
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    unbalanced = True
                    depth = 0
        return max_depth, unbalanced or depth != 0
