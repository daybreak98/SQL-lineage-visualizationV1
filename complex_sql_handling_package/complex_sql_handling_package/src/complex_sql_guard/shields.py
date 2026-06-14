from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .models import Diagnostic, Placeholder, Severity, SourceLocation, SqlTextBundle


@dataclass
class ShieldOptions:
    shield_string_literals: bool = True
    shield_quoted_identifiers: bool = False
    shield_templates: bool = True
    shield_comments: bool = True
    placeholder_prefix: str = "__SQLG"


class OffsetLocator:
    def __init__(self, text: str) -> None:
        self.text = text
        self._line_starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                self._line_starts.append(i + 1)

    def location(self, start: int, end: int) -> SourceLocation:
        import bisect

        start_line_idx = bisect.bisect_right(self._line_starts, start) - 1
        end_line_idx = bisect.bisect_right(self._line_starts, max(end - 1, start)) - 1
        start_line_start = self._line_starts[start_line_idx]
        end_line_start = self._line_starts[end_line_idx]
        return SourceLocation(
            start_offset=start,
            end_offset=end,
            start_line=start_line_idx + 1,
            start_col=start - start_line_start + 1,
            end_line=end_line_idx + 1,
            end_col=end - end_line_start + 1,
        )


class DirtySqlPreprocessor:
    """Protect fragile text fragments before parser sees the SQL.

    This class is deliberately conservative. It shields literals/templates and
    keeps a placeholder mapping so downstream SourceLocation can return to
    original_sql.
    """

    def __init__(self, options: ShieldOptions | None = None) -> None:
        self.options = options or ShieldOptions()

    def preprocess(self, sql: str) -> Tuple[SqlTextBundle, List[Diagnostic]]:
        normalized = self._normalize_reversible(sql)
        locator = OffsetLocator(normalized)
        out: List[str] = []
        placeholders: List[Placeholder] = []
        diagnostics: List[Diagnostic] = []

        i = 0
        n = len(normalized)
        counter = 1
        while i < n:
            ch = normalized[i]
            nxt = normalized[i:i+2]

            # Line comment
            if self.options.shield_comments and nxt == "--":
                end = normalized.find("\n", i)
                if end == -1:
                    end = n
                raw = normalized[i:end]
                ph = self._make_placeholder("COMMENT", counter)
                counter += 1
                placeholders.append(Placeholder(ph, "comment", raw, locator.location(i, end)))
                out.append(" ")
                out.append(ph)
                out.append(" ")
                i = end
                continue

            # Block comment or hint
            if self.options.shield_comments and nxt == "/*":
                end = normalized.find("*/", i + 2)
                if end == -1:
                    end = n
                else:
                    end += 2
                raw = normalized[i:end]
                kind = "hint" if raw.startswith("/*+") else "comment"
                ph = self._make_placeholder("HINT" if kind == "hint" else "COMMENT", counter)
                counter += 1
                placeholders.append(Placeholder(ph, kind, raw, locator.location(i, end)))
                diagnostics.append(Diagnostic(
                    code="HINT_DETECTED" if kind == "hint" else "COMMENT_SHIELDED",
                    severity=Severity.INFO,
                    message=f"{kind} is shielded as {ph}.",
                    stage="preprocess",
                    location=locator.location(i, end),
                ))
                out.append(" ")
                out.append(ph)
                out.append(" ")
                i = end
                continue

            # Template variable ${...} or #{...}
            if self.options.shield_templates and normalized.startswith(("${", "#{"), i):
                end = self._find_balanced_brace(normalized, i + 2)
                raw = normalized[i:end]
                ph = self._make_placeholder("TPL", counter)
                counter += 1
                placeholders.append(Placeholder(ph, "template", raw, locator.location(i, end)))
                diagnostics.append(Diagnostic(
                    code="TEMPLATE_SQL_DETECTED",
                    severity=Severity.WARNING,
                    message=f"Template expression is shielded as {ph}.",
                    stage="preprocess",
                    location=locator.location(i, end),
                ))
                out.append(ph)
                i = end
                continue

            # Freemarker tag <#...> or </#...>
            if self.options.shield_templates and (normalized.startswith("<#", i) or normalized.startswith("</#", i)):
                end = normalized.find(">", i + 2)
                if end == -1:
                    end = n
                else:
                    end += 1
                raw = normalized[i:end]
                ph = self._make_placeholder("FTL", counter)
                counter += 1
                placeholders.append(Placeholder(ph, "template_block_marker", raw, locator.location(i, end)))
                diagnostics.append(Diagnostic(
                    code="TEMPLATE_BLOCK_MARKER_DETECTED",
                    severity=Severity.WARNING,
                    message=f"Template block marker is shielded as {ph}.",
                    stage="preprocess",
                    location=locator.location(i, end),
                ))
                out.append(" ")
                out.append(ph)
                out.append(" ")
                i = end
                continue

            # String literal or double-quoted text.
            # If a quoted literal contains a template expression such as '${DATE}',
            # mark it as template_literal so downstream diagnostics can distinguish
            # ordinary string constants from runtime-substituted SQL.
            if self.options.shield_string_literals and ch in ("'", '"'):
                end = self._find_quoted_end(normalized, i, ch)
                raw = normalized[i:end]
                has_template = "${" in raw or "#{" in raw or "<#" in raw
                ph = self._make_placeholder("TPL" if has_template else "STR", counter)
                counter += 1
                placeholders.append(Placeholder(ph, "template_literal" if has_template else "string_literal", raw, locator.location(i, end)))
                if has_template:
                    diagnostics.append(Diagnostic(
                        code="TEMPLATE_SQL_DETECTED",
                        severity=Severity.WARNING,
                        message=f"Template inside quoted literal is shielded as {ph}.",
                        stage="preprocess",
                        location=locator.location(i, end),
                    ))
                out.append(ph)
                i = end
                continue

            # Backtick identifier; default keep it because parser can often handle it.
            if self.options.shield_quoted_identifiers and ch == "`":
                end = self._find_quoted_end(normalized, i, "`")
                raw = normalized[i:end]
                ph = self._make_placeholder("QID", counter)
                counter += 1
                placeholders.append(Placeholder(ph, "quoted_identifier", raw, locator.location(i, end)))
                out.append(ph)
                i = end
                continue

            out.append(ch)
            i += 1

        analysis_sql = "".join(out)
        bundle = SqlTextBundle(
            original_sql=sql,
            normalized_sql=normalized,
            analysis_sql=analysis_sql,
            placeholders=placeholders,
        )
        return bundle, diagnostics

    def _normalize_reversible(self, sql: str) -> str:
        # Keep this deliberately minimal. More aggressive normalization must
        # carry a true offset mapper.
        return sql.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")

    def _make_placeholder(self, kind: str, counter: int) -> str:
        return f"{self.options.placeholder_prefix}_{kind}_{counter:04d}__"

    def _find_quoted_end(self, text: str, start: int, quote: str) -> int:
        i = start + 1
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == "\\":
                i += 2
                continue
            # SQL escaped single quote: ''
            if quote == "'" and ch == "'" and i + 1 < n and text[i + 1] == "'":
                i += 2
                continue
            if ch == quote:
                return i + 1
            i += 1
        return n

    def _find_balanced_brace(self, text: str, start: int) -> int:
        depth = 1
        i = start
        n = len(text)
        in_single = False
        in_double = False
        while i < n:
            ch = text[i]
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif not in_single and not in_double:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i + 1
            i += 1
        return n
