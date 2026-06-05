from __future__ import annotations

from dataclasses import dataclass
import re

from . import diagnostics as diag_codes
from .models import Diagnostic, PreflightReport, Severity


@dataclass(frozen=True)
class PreflightOptions:
    max_sql_chars: int = 200_000
    warn_sql_chars: int = 50_000
    warn_line_count: int = 800
    complex_score_threshold: int = 8


class PreflightChecker:
    _TEMPLATE_RE = re.compile(r"\$\{[^}]+\}|#\{[^}]+\}|<#.*?>|</#.*?>", re.IGNORECASE | re.DOTALL)
    _ROW_EXPANDING_RE = re.compile(r"\b(lateral\s+view|explode|posexplode|inline)\b", re.IGNORECASE)
    _REGEX_FUNCTION_RE = re.compile(r"\b(regexp_extract|regexp_replace)\s*\(", re.IGNORECASE)
    _JSON_FUNCTION_RE = re.compile(r"\b(get_json_object|json_tuple|from_json)\s*\(", re.IGNORECASE)
    _JOIN_RE = re.compile(r"\bjoin\b", re.IGNORECASE)
    _UNION_RE = re.compile(r"\bunion(?:\s+all)?\b", re.IGNORECASE)
    _SUBQUERY_RE = re.compile(r"\(\s*select\b", re.IGNORECASE)

    def __init__(self, options: PreflightOptions | None = None) -> None:
        self.options = options or PreflightOptions()

    def check(self, sql: str) -> PreflightReport:
        diagnostics: list[Diagnostic] = []
        risk_flags: list[str] = []
        char_count = len(sql)
        line_count = sql.count("\n") + 1 if sql else 0
        max_parentheses_depth, parentheses_balanced = self._scan_parentheses(sql)
        quotes_balanced = self._scan_quotes(sql)

        contains_templates = bool(self._TEMPLATE_RE.search(sql))
        contains_freemarker = "<#" in sql or "</#" in sql
        contains_lateral_view = bool(self._ROW_EXPANDING_RE.search(sql))
        contains_regex_functions = bool(self._REGEX_FUNCTION_RE.search(sql))
        contains_json_functions = bool(self._JSON_FUNCTION_RE.search(sql))
        contains_invisible_characters = any(char in sql for char in ("\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"))
        complexity_score = self._complexity_score(sql)

        if char_count > self.options.warn_sql_chars or line_count > self.options.warn_line_count:
            risk_flags.append(diag_codes.LONG_SQL_DETECTED)
            diagnostics.append(Diagnostic(
                code=diag_codes.LONG_SQL_DETECTED,
                severity=Severity.WARNING,
                message=f"SQL is large ({char_count} chars / {line_count} lines); defensive parsing is enabled.",
                stage="preflight",
                confidence=0.95,
            ))

        if complexity_score >= self.options.complex_score_threshold:
            risk_flags.append(diag_codes.COMPLEX_SQL_DETECTED)
            diagnostics.append(Diagnostic(
                code=diag_codes.COMPLEX_SQL_DETECTED,
                severity=Severity.INFO,
                message=f"Complex SQL structure detected (score={complexity_score}).",
                stage="preflight",
                confidence=0.9,
            ))

        if not parentheses_balanced:
            risk_flags.append(diag_codes.UNBALANCED_PARENTHESES_WARNING)
            diagnostics.append(Diagnostic(
                code=diag_codes.UNBALANCED_PARENTHESES_WARNING,
                severity=Severity.WARNING,
                message="Parentheses appear to be unbalanced in a coarse scan.",
                stage="preflight",
                confidence=0.8,
            ))

        if not quotes_balanced:
            risk_flags.append(diag_codes.UNBALANCED_QUOTES_WARNING)
            diagnostics.append(Diagnostic(
                code=diag_codes.UNBALANCED_QUOTES_WARNING,
                severity=Severity.WARNING,
                message="Quotes appear to be unbalanced in a coarse scan.",
                stage="preflight",
                confidence=0.8,
            ))

        if contains_templates:
            risk_flags.append(diag_codes.TEMPLATE_SQL_DETECTED)
            diagnostics.append(Diagnostic(
                code=diag_codes.TEMPLATE_SQL_DETECTED,
                severity=Severity.WARNING,
                message="Template variables or template blocks are detected.",
                stage="preflight",
                confidence=0.95,
            ))

        if contains_freemarker:
            risk_flags.append(diag_codes.FREEMARKER_BLOCK_DETECTED)
            diagnostics.append(Diagnostic(
                code=diag_codes.FREEMARKER_BLOCK_DETECTED,
                severity=Severity.WARNING,
                message="Freemarker control blocks are detected.",
                stage="preflight",
                confidence=0.95,
            ))

        if contains_lateral_view:
            risk_flags.append(diag_codes.ROW_EXPANDING_FUNCTION)
            diagnostics.append(Diagnostic(
                code=diag_codes.ROW_EXPANDING_FUNCTION,
                severity=Severity.INFO,
                message="Row-expanding functions such as lateral view/explode are detected.",
                stage="preflight",
                confidence=0.95,
            ))

        if contains_regex_functions:
            diagnostics.append(Diagnostic(
                code=diag_codes.REGEX_FUNCTION_DETECTED,
                severity=Severity.INFO,
                message="Regex functions are detected.",
                stage="preflight",
                confidence=0.95,
            ))

        if contains_json_functions:
            diagnostics.append(Diagnostic(
                code=diag_codes.JSON_FUNCTION_DETECTED,
                severity=Severity.INFO,
                message="JSON functions are detected.",
                stage="preflight",
                confidence=0.95,
            ))

        if contains_invisible_characters:
            risk_flags.append(diag_codes.INVISIBLE_CHARACTER_DETECTED)
            diagnostics.append(Diagnostic(
                code=diag_codes.INVISIBLE_CHARACTER_DETECTED,
                severity=Severity.WARNING,
                message="Invisible characters are detected and will be normalized conservatively.",
                stage="preflight",
                confidence=0.9,
            ))

        if char_count > self.options.max_sql_chars:
            diagnostics.append(Diagnostic(
                code=diag_codes.ANALYSIS_TIMEOUT,
                severity=Severity.ERROR,
                message=(
                    f"SQL length {char_count} exceeds the configured defensive threshold "
                    f"{self.options.max_sql_chars}; downstream parsing confidence is low."
                ),
                stage="preflight",
                confidence=0.7,
            ))

        return PreflightReport(
            char_count=char_count,
            line_count=line_count,
            max_parentheses_depth=max_parentheses_depth,
            quote_balance_ok=quotes_balanced,
            contains_templates=contains_templates,
            contains_lateral_view=contains_lateral_view,
            contains_regex_functions=contains_regex_functions,
            contains_json_functions=contains_json_functions,
            contains_invisible_characters=contains_invisible_characters,
            complexity_score=complexity_score,
            risk_flags=risk_flags,
            diagnostics=diagnostics,
        )

    def _complexity_score(self, sql: str) -> int:
        lowered = sql.lower()
        cte_bonus = 2 if lowered.lstrip().startswith("with ") else 0
        return (
            cte_bonus
            + len(self._JOIN_RE.findall(sql))
            + len(self._UNION_RE.findall(sql))
            + len(self._SUBQUERY_RE.findall(sql))
            + len(self._ROW_EXPANDING_RE.findall(sql)) * 2
            + len(self._REGEX_FUNCTION_RE.findall(sql))
            + len(self._JSON_FUNCTION_RE.findall(sql))
            + len(self._TEMPLATE_RE.findall(sql)) * 2
        )

    def _scan_parentheses(self, sql: str) -> tuple[int, bool]:
        depth = 0
        max_depth = 0
        in_single = False
        in_double = False
        in_backtick = False
        escaped = False

        for char in sql:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == "'" and not in_double and not in_backtick:
                in_single = not in_single
                continue
            if char == '"' and not in_single and not in_backtick:
                in_double = not in_double
                continue
            if char == "`" and not in_single and not in_double:
                in_backtick = not in_backtick
                continue
            if in_single or in_double or in_backtick:
                continue
            if char == "(":
                depth += 1
                max_depth = max(max_depth, depth)
            elif char == ")":
                depth -= 1
                if depth < 0:
                    return max_depth, False

        return max_depth, depth == 0

    def _scan_quotes(self, sql: str) -> bool:
        in_single = False
        in_double = False
        in_backtick = False
        escaped = False
        index = 0

        while index < len(sql):
            char = sql[index]
            if escaped:
                escaped = False
                index += 1
                continue
            if char == "\\":
                escaped = True
                index += 1
                continue
            if char == "'" and not in_double and not in_backtick:
                if index + 1 < len(sql) and sql[index + 1] == "'":
                    index += 2
                    continue
                in_single = not in_single
                index += 1
                continue
            if char == '"' and not in_single and not in_backtick:
                in_double = not in_double
                index += 1
                continue
            if char == "`" and not in_single and not in_double:
                in_backtick = not in_backtick
                index += 1
                continue
            index += 1

        return not (in_single or in_double or in_backtick)

