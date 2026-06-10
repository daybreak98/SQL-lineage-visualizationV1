import time
import re
from dataclasses import dataclass

from fastapi import APIRouter

from app.models import ConvertSqlRequest, ConvertSqlResponse, Diagnostic, FormatSqlRequest, FormatSqlResponse

router = APIRouter()


SUPPORTED_DIALECTS = {"spark", "hive", "starrocks"}
ALIASES = {"sr": "starrocks"}
RISKY_FUNCTIONS_BY_TARGET = {
    "hive": {"bitmap_count", "to_bitmap"},
    "spark": {"bitmap_count", "to_bitmap"},
    "starrocks": {"lateral_view", "explode", "posexplode"},
}
CASE_PRESERVED_WORDS = {
    "select",
    "from",
    "where",
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "on",
    "as",
    "group",
    "by",
    "order",
    "having",
    "with",
    "insert",
    "overwrite",
    "table",
    "partition",
    "count",
    "sum",
    "avg",
    "min",
    "max",
    "distinct",
    "case",
    "when",
    "then",
    "else",
    "end",
    "if",
    "ifnull",
    "coalesce",
    "from_unixtime",
    "date_format",
}


@dataclass(frozen=True)
class DialectNormalization:
    raw: str
    normalized: str
    diagnostic: Diagnostic | None = None


def _normalize_dialect(dialect: str) -> DialectNormalization:
    value = dialect.strip().lower()
    normalized = ALIASES.get(value, value)
    if normalized in SUPPORTED_DIALECTS:
        return DialectNormalization(raw=value, normalized=normalized)
    return DialectNormalization(
        raw=value,
        normalized=value,
        diagnostic=Diagnostic(
            code="UNSUPPORTED_DIALECT",
            level="error",
            message=(
                f"Unsupported SQL dialect: {dialect}. "
                f"Supported dialects are: {', '.join(sorted(SUPPORTED_DIALECTS))}."
            ),
        ),
    )


@router.post("/sql/format", response_model=FormatSqlResponse)
async def format_sql(request: FormatSqlRequest) -> FormatSqlResponse:
    import sqlglot

    dialect = _normalize_dialect(request.dialect)
    if dialect.diagnostic is not None:
        return FormatSqlResponse(
            status="failed",
            dialect=dialect.normalized,
            formatted_sql=None,
            diagnostics=[dialect.diagnostic],
        )

    try:
        formatted = sqlglot.transpile(
            request.sql,
            read=dialect.normalized,
            write=dialect.normalized,
            pretty=True,
        )[0]
        return FormatSqlResponse(
            status="success",
            dialect=dialect.normalized,
            formatted_sql=formatted,
            diagnostics=[],
        )
    except Exception as e:
        return FormatSqlResponse(
            status="failed",
            dialect=dialect.normalized,
            formatted_sql=None,
            diagnostics=[
                Diagnostic(
                    code="SQL_FORMAT_ERROR",
                    level="error",
                    message=str(e),
                )
            ],
        )


@router.post("/sql/convert", response_model=ConvertSqlResponse)
async def convert_sql(request: ConvertSqlRequest) -> ConvertSqlResponse:
    import sqlglot

    started = time.perf_counter()
    source_dialect = _normalize_dialect(request.source_dialect)
    target_dialect = _normalize_dialect(request.target_dialect)
    dialect_diagnostics = [
        diagnostic
        for diagnostic in [source_dialect.diagnostic, target_dialect.diagnostic]
        if diagnostic is not None
    ]
    if dialect_diagnostics:
        return ConvertSqlResponse(
            status="failed",
            source_dialect=source_dialect.normalized,
            target_dialect=target_dialect.normalized,
            converted_sql=None,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            diagnostics=dialect_diagnostics,
        )

    try:
        converted = sqlglot.transpile(
            request.sql,
            read=source_dialect.normalized,
            write=target_dialect.normalized,
            pretty=request.pretty,
        )[0]
        converted = _minimize_diff_noise(
            request.sql,
            converted,
            keep_original_if_noop=not request.pretty,
        )
        diagnostics = _conversion_diagnostics(
            sqlglot=sqlglot,
            source_sql=request.sql,
            converted_sql=converted,
            target_dialect=target_dialect.normalized,
        )
        return ConvertSqlResponse(
            status="partial" if diagnostics else "success",
            source_dialect=source_dialect.normalized,
            target_dialect=target_dialect.normalized,
            converted_sql=converted,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            diagnostics=diagnostics,
        )
    except Exception as exc:
        return ConvertSqlResponse(
            status="failed",
            source_dialect=source_dialect.normalized,
            target_dialect=target_dialect.normalized,
            converted_sql=None,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            diagnostics=[
                Diagnostic(
                    code="SQL_CONVERT_ERROR",
                    level="error",
                    message=str(exc),
                )
            ],
        )


def _conversion_diagnostics(sqlglot, source_sql: str, converted_sql: str, target_dialect: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = _source_function_diagnostics(source_sql, target_dialect)
    try:
        sqlglot.parse_one(converted_sql, read=target_dialect)
    except Exception as exc:
        diagnostics.append(
            Diagnostic(
                code="TARGET_PARSE_WARNING",
                level="warning",
                message=f"Converted SQL could not be parsed as {target_dialect}: {exc}",
            )
        )

    lowered = converted_sql.lower()
    for function_name in sorted(RISKY_FUNCTIONS_BY_TARGET.get(target_dialect, set())):
        if f"{function_name}(" in lowered:
            diagnostics.append(
                Diagnostic(
                    code="FUNCTION_PASSTHROUGH",
                    level="warning",
                    message=(
                        f"Function {function_name} remains in converted SQL. "
                        f"Verify compatibility with target dialect {target_dialect}."
                    ),
                    extra={"function": function_name, "target_dialect": target_dialect},
                )
            )
    return diagnostics


def _source_function_diagnostics(source_sql: str, target_dialect: str) -> list[Diagnostic]:
    risky_functions = RISKY_FUNCTIONS_BY_TARGET.get(target_dialect, set())
    if not risky_functions:
        return []

    diagnostics: list[Diagnostic] = []
    seen: set[tuple[str, int]] = set()
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(function_name) for function_name in sorted(risky_functions, key=len, reverse=True)) + r")\s*\(",
        flags=re.IGNORECASE,
    )
    line_starts = _line_starts(source_sql)

    for match in pattern.finditer(source_sql):
        function_name = match.group(1)
        line = _line_for_offset(line_starts, match.start())
        key = (function_name.lower(), line)
        if key in seen:
            continue
        seen.add(key)
        diagnostics.append(
            Diagnostic(
                code="FUNCTION_CONVERSION_UNCERTAIN",
                level="warning",
                message=(
                    f"Line {line}: function {function_name} is not guaranteed to convert correctly "
                    f"for target dialect {target_dialect}."
                ),
                location={"line": line, "col": match.start() - line_starts[line - 1] + 1},
                extra={"function": function_name, "target_dialect": target_dialect},
            )
        )
    return diagnostics


def _line_starts(sql: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(sql):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _line_for_offset(line_starts: list[int], offset: int) -> int:
    line = 1
    for index, start in enumerate(line_starts, start=1):
        if start > offset:
            break
        line = index
    return line


def _minimize_diff_noise(source_sql: str, converted_sql: str, *, keep_original_if_noop: bool) -> str:
    if keep_original_if_noop and _case_and_space_insensitive(source_sql) == _case_and_space_insensitive(converted_sql):
        return source_sql
    return _restore_source_word_case(source_sql, converted_sql)


def _case_and_space_insensitive(sql: str) -> str:
    return re.sub(r"\s+", "", sql).lower()


def _restore_source_word_case(source_sql: str, converted_sql: str) -> str:
    source_case: dict[str, str] = {}
    for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", source_sql):
        word = match.group(0)
        lower = word.lower()
        if lower in CASE_PRESERVED_WORDS and lower not in source_case:
            source_case[lower] = word

    if not source_case:
        return converted_sql

    pattern = re.compile(
        r"\b(" + "|".join(re.escape(word) for word in sorted(source_case, key=len, reverse=True)) + r")\b",
        flags=re.IGNORECASE,
    )

    def replace(match: re.Match[str]) -> str:
        return source_case.get(match.group(0).lower(), match.group(0))

    return pattern.sub(replace, converted_sql)
