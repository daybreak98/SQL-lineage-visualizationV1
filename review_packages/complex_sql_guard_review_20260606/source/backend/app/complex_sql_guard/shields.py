from __future__ import annotations

from dataclasses import dataclass
import re

from . import diagnostics as diag_codes
from .models import Diagnostic, OffsetMapping, Placeholder, Severity, SqlTextBundle
from .normalizer import OffsetLocator, map_offset, map_span_to_original, normalize_sql_reversible


@dataclass(frozen=True)
class ShieldOptions:
    shield_string_literals: bool = True
    shield_quoted_identifiers: bool = False
    shield_templates: bool = True
    shield_comments: bool = True
    placeholder_prefix: str = "__SQLG"


class DirtySqlPreprocessor:
    _REGEX_CONTEXT_RE = re.compile(r"(regexp_extract|regexp_replace)\s*\([^)]*$", re.IGNORECASE)
    _JSON_CONTEXT_RE = re.compile(r"(get_json_object|json_tuple|from_json)\s*\([^)]*$", re.IGNORECASE)

    def __init__(self, options: ShieldOptions | None = None) -> None:
        self.options = options or ShieldOptions()

    def preprocess(self, sql: str) -> tuple[SqlTextBundle, list[Diagnostic]]:
        normalized = normalize_sql_reversible(sql)
        original_locator = OffsetLocator(sql)
        analysis_chars: list[str] = []
        analysis_to_original: list[int] = []
        placeholders: list[Placeholder] = []
        diagnostics: list[Diagnostic] = []

        index = 0
        counter = 1
        normalized_sql = normalized.text
        original_length = len(sql)

        while index < len(normalized_sql):
            char = normalized_sql[index]
            next_two = normalized_sql[index:index + 2]

            if self.options.shield_comments and next_two == "--":
                end = normalized_sql.find("\n", index)
                if end < 0:
                    end = len(normalized_sql)
                placeholder = self._make_placeholder("COMMENT", counter)
                counter += 1
                self._record_blank_replacement(
                    analysis_chars,
                    analysis_to_original,
                    normalized,
                    normalized_sql[index:end],
                    index,
                    placeholder,
                    "comment",
                    original_locator,
                    placeholders,
                    diagnostics,
                    diag_codes.COMMENT_SHIELD_APPLIED,
                    "Line comment is shielded for defensive parsing.",
                )
                index = end
                continue

            if self.options.shield_comments and next_two == "/*":
                end = normalized_sql.find("*/", index + 2)
                if end < 0:
                    end = len(normalized_sql)
                else:
                    end += 2
                raw = normalized_sql[index:end]
                is_hint = raw.startswith("/*+")
                placeholder = self._make_placeholder("HINT" if is_hint else "COMMENT", counter)
                counter += 1
                self._record_blank_replacement(
                    analysis_chars,
                    analysis_to_original,
                    normalized,
                    raw,
                    index,
                    placeholder,
                    "hint" if is_hint else "comment",
                    original_locator,
                    placeholders,
                    diagnostics,
                    diag_codes.HINT_SHIELD_APPLIED if is_hint else diag_codes.COMMENT_SHIELD_APPLIED,
                    "Optimizer hint is shielded for defensive parsing." if is_hint else "Block comment is shielded for defensive parsing.",
                )
                index = end
                continue

            if self.options.shield_templates and normalized_sql.startswith(("${", "#{"), index):
                end = self._find_balanced_brace(normalized_sql, index + 2)
                raw = normalized_sql[index:end]
                placeholder = self._make_placeholder("TPL", counter)
                counter += 1
                self._record_placeholder_replacement(
                    analysis_chars,
                    analysis_to_original,
                    placeholder,
                    normalized,
                    index,
                    end,
                    "template",
                    raw,
                    original_locator,
                    placeholders,
                    diagnostics,
                    Diagnostic(
                        code=diag_codes.TEMPLATE_SQL_DETECTED,
                        severity=Severity.WARNING,
                        message=f"Template expression is shielded as {placeholder}.",
                        stage="preprocess",
                        location=self._location(original_locator, normalized, index, end),
                        confidence=0.95,
                    ),
                )
                index = end
                continue

            if self.options.shield_templates and (normalized_sql.startswith("<#", index) or normalized_sql.startswith("</#", index)):
                end = normalized_sql.find(">", index + 2)
                if end < 0:
                    end = len(normalized_sql)
                else:
                    end += 1
                raw = normalized_sql[index:end]
                placeholder = self._make_placeholder("FTL", counter)
                counter += 1
                self._record_blank_replacement(
                    analysis_chars,
                    analysis_to_original,
                    normalized,
                    raw,
                    index,
                    placeholder,
                    "freemarker_block",
                    original_locator,
                    placeholders,
                    diagnostics,
                    diag_codes.FREEMARKER_BLOCK_DETECTED,
                    "Freemarker control block marker is shielded for defensive parsing.",
                )
                index = end
                continue

            if self.options.shield_string_literals and char in ("'", '"'):
                end = self._find_quoted_end(normalized_sql, index, char)
                raw = normalized_sql[index:end]
                label, kind, code, severity, message = self._classify_literal(normalized_sql[:index], raw)
                placeholder = self._make_placeholder(label, counter)
                counter += 1
                self._record_placeholder_replacement(
                    analysis_chars,
                    analysis_to_original,
                    placeholder,
                    normalized,
                    index,
                    end,
                    kind,
                    raw,
                    original_locator,
                    placeholders,
                    diagnostics,
                    Diagnostic(
                        code=code,
                        severity=severity,
                        message=message.format(placeholder=placeholder),
                        stage="preprocess",
                        confidence=0.95,
                    ),
                )
                index = end
                continue

            if self.options.shield_quoted_identifiers and char == "`":
                end = self._find_quoted_end(normalized_sql, index, "`")
                raw = normalized_sql[index:end]
                placeholder = self._make_placeholder("QID", counter)
                counter += 1
                self._record_placeholder_replacement(
                    analysis_chars,
                    analysis_to_original,
                    placeholder,
                    normalized,
                    index,
                    end,
                    "quoted_identifier",
                    raw,
                    original_locator,
                    placeholders,
                    diagnostics,
                    Diagnostic(
                        code=diag_codes.LITERAL_SHIELD_APPLIED,
                        severity=Severity.INFO,
                        message=f"Quoted identifier is shielded as {placeholder}.",
                        stage="preprocess",
                        location=self._location(original_locator, normalized, index, end),
                        confidence=0.9,
                    ),
                )
                index = end
                continue

            analysis_chars.append(char)
            analysis_to_original.append(map_offset(normalized.char_to_original, index, original_length))
            index += 1

        bundle = SqlTextBundle(
            original_sql=sql,
            normalized_sql=normalized_sql,
            analysis_sql="".join(analysis_chars),
            placeholders=placeholders,
            offset_mapping=OffsetMapping(
                original_length=original_length,
                normalized_to_original=normalized.char_to_original,
                analysis_to_original=analysis_to_original,
            ),
        )
        return bundle, diagnostics

    def _classify_literal(self, before_text: str, raw_text: str) -> tuple[str, str, str, Severity, str]:
        if "${" in raw_text or "#{" in raw_text or "<#" in raw_text:
            return (
                "TPL",
                "template_literal",
                diag_codes.TEMPLATE_SQL_DETECTED,
                Severity.WARNING,
                "Template literal is shielded as {placeholder}.",
            )

        tail = before_text[-256:].lower()
        if raw_text.startswith(("'$.", "\"$.", "'$[", "\"$[")) or self._JSON_CONTEXT_RE.search(tail):
            return (
                "JSON",
                "json_path_literal",
                diag_codes.JSON_PATH_LITERAL_SHIELD_APPLIED,
                Severity.INFO,
                "JSON path literal is shielded as {placeholder}.",
            )

        if self._REGEX_CONTEXT_RE.search(tail):
            return (
                "REGEX",
                "regex_literal",
                diag_codes.REGEX_LITERAL_SHIELD_APPLIED,
                Severity.INFO,
                "Regex literal is shielded as {placeholder}.",
            )

        return (
            "STR",
            "string_literal",
            diag_codes.LITERAL_SHIELD_APPLIED,
            Severity.INFO,
            "String literal is shielded as {placeholder}.",
        )

    def _record_blank_replacement(
        self,
        analysis_chars: list[str],
        analysis_to_original: list[int],
        normalized,
        raw_text: str,
        span_start: int,
        placeholder: str,
        kind: str,
        original_locator: OffsetLocator,
        placeholders: list[Placeholder],
        diagnostics: list[Diagnostic],
        diagnostic_code: str,
        diagnostic_message: str,
    ) -> None:
        span_end = span_start + len(raw_text)
        location = self._location(original_locator, normalized, span_start, span_end)
        placeholders.append(Placeholder(placeholder=placeholder, kind=kind, raw_text=raw_text, location=location))
        diagnostics.append(Diagnostic(
            code=diagnostic_code,
            severity=Severity.INFO,
            message=diagnostic_message,
            stage="preprocess",
            location=location,
            confidence=0.95,
        ))

        replacement = self._blank_like(raw_text)
        for offset, char in enumerate(replacement):
            analysis_chars.append(char)
            analysis_to_original.append(map_offset(normalized.char_to_original, span_start + offset, len(original_locator.text)))

    def _record_placeholder_replacement(
        self,
        analysis_chars: list[str],
        analysis_to_original: list[int],
        placeholder: str,
        normalized,
        span_start: int,
        span_end: int,
        kind: str,
        raw_text: str,
        original_locator: OffsetLocator,
        placeholders: list[Placeholder],
        diagnostics: list[Diagnostic],
        diagnostic: Diagnostic,
    ) -> None:
        location = self._location(original_locator, normalized, span_start, span_end)
        placeholders.append(Placeholder(placeholder=placeholder, kind=kind, raw_text=raw_text, location=location))
        diagnostic.location = location
        diagnostics.append(diagnostic)
        original_start, _ = map_span_to_original(normalized.char_to_original, span_start, span_end, len(original_locator.text))
        for char in placeholder:
            analysis_chars.append(char)
            analysis_to_original.append(original_start)

    def _location(self, locator: OffsetLocator, normalized, span_start: int, span_end: int):
        original_start, original_end = map_span_to_original(
            normalized.char_to_original,
            span_start,
            span_end,
            len(locator.text),
        )
        return locator.location(original_start, original_end)

    def _blank_like(self, raw_text: str) -> str:
        return "".join("\n" if char == "\n" else "\t" if char == "\t" else " " for char in raw_text)

    def _make_placeholder(self, kind_label: str, counter: int) -> str:
        return f"{self.options.placeholder_prefix}_{kind_label}_{counter:04d}__"

    def _find_balanced_brace(self, text: str, start: int) -> int:
        depth = 1
        index = start
        in_single = False
        in_double = False
        while index < len(text):
            char = text[index]
            if char == "'" and not in_double:
                in_single = not in_single
            elif char == '"' and not in_single:
                in_double = not in_double
            elif not in_single and not in_double:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return index + 1
            index += 1
        return len(text)

    def _find_quoted_end(self, text: str, start: int, quote: str) -> int:
        index = start + 1
        while index < len(text):
            char = text[index]
            if char == "\\":
                index += 2
                continue
            if quote == "'" and char == "'" and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            if char == quote:
                return index + 1
            index += 1
        return len(text)
