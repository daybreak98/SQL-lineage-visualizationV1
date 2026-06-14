from __future__ import annotations

from dataclasses import dataclass, field
import re

from . import diagnostics as diag_codes
from .models import Diagnostic, Severity


_SET_RE = re.compile(r"(?is)^\s*set\b")
_ADD_JAR_RE = re.compile(r"(?is)^\s*add\s+jar\b")
_USE_RE = re.compile(r"(?is)^\s*use\b")
_TEMP_UDF_RE = re.compile(r"(?is)^\s*create\s+temporary\s+function\b")
_DDL_RE = re.compile(r"(?is)^\s*(create|drop|alter|truncate|msck|repair)\b")
_INSERT_HEAD_RE = re.compile(
    r"(?is)^\s*insert\s+(overwrite|into)\s+(?:table\s+)?(?P<table>(?:`[^`]+`|[A-Za-z_][\w]*)(?:\.(?:`[^`]+`|[A-Za-z_][\w]*)){0,2})"
)
_PARTITION_RE = re.compile(r"(?is)\bpartition\s*\(")
_QUERY_RE = re.compile(r"(?is)^\s*(with|select)\b")


@dataclass(frozen=True)
class ScriptStatement:
    index: int
    statement_type: str
    sql: str
    start_offset: int
    end_offset: int
    diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass(frozen=True)
class ScriptSelection:
    analysis_sql: str
    start_offset: int
    end_offset: int
    selected_target: str
    selected_kind: str
    statement_count: int
    skipped_count: int
    diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass
class SkippedStatement:
    statement_type: str
    sql_snippet: str
    start_offset: int
    end_offset: int


@dataclass
class InsertTarget:
    target_table: str
    partition_spec: str | None = None
    is_overwrite: bool = True


@dataclass
class CleanedSqlScript:
    original_sql: str
    analyzable_sql: str
    skipped_statements: list[SkippedStatement] = field(default_factory=list)
    insert_target: InsertTarget | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)


def clean_sql_script(sql: str) -> CleanedSqlScript:
    """前置于 complex_sql_guard 的脚本清洗入口。
    拆分壳语句和可分析查询，输出统一的 CleanedSqlScript。
    """
    selection = select_analysis_statement(sql)
    skipped: list[SkippedStatement] = []
    insert_target = _extract_insert_target_from_sql(sql)

    return CleanedSqlScript(
        original_sql=sql,
        analyzable_sql=selection.analysis_sql,
        skipped_statements=skipped,
        insert_target=insert_target,
        diagnostics=list(selection.diagnostics),
    )


def _extract_insert_target_from_sql(sql: str) -> InsertTarget | None:
    m = re.search(r"(?ims)\binsert\s+(overwrite|into)\s+(?:table\s+)?(?P<table>(?:`[^`]+`|[A-Za-z_][\w]*)(?:\.(?:`[^`]+`|[A-Za-z_][\w]*)){0,2})", sql)
    if m is None:
        return None
    is_overwrite = m.group(1).lower() == "overwrite"
    partition_spec = None
    pm = _PARTITION_RE.search(sql, pos=m.end())
    if pm is not None:
        partition_spec = sql[pm.start():pm.end()]
    return InsertTarget(target_table=m.group("table"), partition_spec=partition_spec, is_overwrite=is_overwrite)


def select_analysis_statement(sql: str) -> ScriptSelection:
    statements = _split_statements(sql)
    classified = [_classify_statement(statement) for statement in statements]

    diagnostics: list[Diagnostic] = []
    for statement in classified:
        diagnostics.extend(statement.diagnostics)

    if len(classified) > 1:
        diagnostics.append(Diagnostic(
            code=diag_codes.MULTI_STATEMENT_SCRIPT_DETECTED,
            severity=Severity.INFO,
            message=f"Detected {len(classified)} SQL statements; selecting the last analyzable statement.",
            stage="statement_clean",
            confidence=0.95,
            extra={"statement_count": len(classified)},
        ))

    candidates = [_candidate_from_statement(statement) for statement in classified]
    analyzable = [candidate for candidate in candidates if candidate is not None]
    selected = analyzable[-1] if analyzable else None
    skipped_count = sum(1 for statement in classified if statement.statement_type not in {"query", "insert"})

    if selected is None:
        return ScriptSelection(
            analysis_sql=sql,
            start_offset=0,
            end_offset=len(sql),
            selected_target="analysis_sql",
            selected_kind="full_script",
            statement_count=len(classified),
            skipped_count=skipped_count,
            diagnostics=diagnostics,
        )

    diagnostics.extend(selected.diagnostics)
    diagnostics.append(Diagnostic(
        code=diag_codes.ANALYSIS_STATEMENT_SELECTED,
        severity=Severity.INFO,
        message=f"Selected {selected.selected_kind} for guarded parsing.",
        stage="statement_clean",
        confidence=0.95,
        extra={
            "selected_target": selected.selected_target,
            "statement_count": len(classified),
            "skipped_count": skipped_count,
        },
    ))
    return ScriptSelection(
        analysis_sql=selected.analysis_sql,
        start_offset=selected.start_offset,
        end_offset=selected.end_offset,
        selected_target=selected.selected_target,
        selected_kind=selected.selected_kind,
        statement_count=len(classified),
        skipped_count=skipped_count,
        diagnostics=diagnostics,
    )


def _split_statements(sql: str) -> list[ScriptStatement]:
    statements: list[ScriptStatement] = []
    start = 0
    quote: str | None = None
    index = 0

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if quote == "'" and char == "'" and next_char == "'":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue

        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            continue

        if char == ";":
            statement = _make_statement(sql, start, index)
            if statement is not None:
                statements.append(statement)
            start = index + 1
        index += 1

    statement = _make_statement(sql, start, len(sql))
    if statement is not None:
        statements.append(statement)
    return [
        ScriptStatement(
            index=index,
            statement_type=statement.statement_type,
            sql=statement.sql,
            start_offset=statement.start_offset,
            end_offset=statement.end_offset,
            diagnostics=statement.diagnostics,
        )
        for index, statement in enumerate(statements)
    ]


def _make_statement(sql: str, start: int, end: int) -> ScriptStatement | None:
    raw = sql[start:end]
    trimmed = raw.strip()
    if not trimmed:
        return None
    left_trim = len(raw) - len(raw.lstrip())
    right_trim = len(raw) - len(raw.rstrip())
    return ScriptStatement(
        index=0,
        statement_type="unknown",
        sql=trimmed,
        start_offset=start + left_trim,
        end_offset=max(start + left_trim, end - right_trim),
    )


def _classify_statement(statement: ScriptStatement) -> ScriptStatement:
    sql = statement.sql
    diagnostics: list[Diagnostic] = []
    statement_type = "unknown"

    if _SET_RE.match(sql) or _ADD_JAR_RE.match(sql) or _USE_RE.match(sql):
        statement_type = "exec_config"
        diagnostics.append(Diagnostic(
            code=diag_codes.NON_ANALYSIS_STATEMENT_SKIPPED,
            severity=Severity.INFO,
            message="Execution/config statement skipped from lineage parsing.",
            stage="statement_clean",
            confidence=1.0,
            extra={"statement_type": statement_type},
        ))
    elif _TEMP_UDF_RE.match(sql):
        statement_type = "temp_udf"
        diagnostics.append(Diagnostic(
            code=diag_codes.TEMP_UDF_REGISTERED,
            severity=Severity.INFO,
            message="Temporary UDF registration detected before analyzable SQL.",
            stage="statement_clean",
            confidence=0.95,
        ))
    elif _INSERT_HEAD_RE.match(sql):
        statement_type = "insert"
    elif _QUERY_RE.match(sql):
        statement_type = "query"
    elif _DDL_RE.match(sql):
        statement_type = "ddl"
        diagnostics.append(Diagnostic(
            code=diag_codes.NON_ANALYSIS_STATEMENT_SKIPPED,
            severity=Severity.INFO,
            message="DDL statement skipped from lineage parsing.",
            stage="statement_clean",
            confidence=1.0,
            extra={"statement_type": statement_type},
        ))
    else:
        diagnostics.append(Diagnostic(
            code=diag_codes.UNKNOWN_STATEMENT_TYPE,
            severity=Severity.WARNING,
            message="Unable to classify statement during guarded cleaning.",
            stage="statement_clean",
            confidence=0.6,
        ))

    return ScriptStatement(
        index=statement.index,
        statement_type=statement_type,
        sql=statement.sql,
        start_offset=statement.start_offset,
        end_offset=statement.end_offset,
        diagnostics=diagnostics,
    )


def _candidate_from_statement(statement: ScriptStatement) -> ScriptSelection | None:
    if statement.statement_type == "query":
        insert_m = re.search(r"(?ims)\binsert\s+(overwrite|into)\b", statement.sql)
        if insert_m is not None:
            extracted = _extract_insert_source(statement)
            if extracted is not None and extracted.analysis_sql:
                return extracted
        return ScriptSelection(
            analysis_sql=statement.sql,
            start_offset=statement.start_offset,
            end_offset=statement.end_offset,
            selected_target=f"statement_{statement.index:04d}",
            selected_kind="query_statement",
            statement_count=1,
            skipped_count=0,
        )

    if statement.statement_type != "insert":
        return None

    insert_target = _extract_insert_source(statement)
    if insert_target is None:
        return None
    return insert_target


def _extract_insert_source(statement: ScriptStatement) -> ScriptSelection | None:
    match = re.search(r"(?ims)\binsert\s+(overwrite|into)\s+(?:table\s+)?(?P<table>(?:`[^`]+`|[A-Za-z_][\w]*)(?:\.(?:`[^`]+`|[A-Za-z_][\w]*)){0,2})", statement.sql)
    if match is None:
        return None
    source_start = match.end()
    diagnostics: list[Diagnostic] = [
        Diagnostic(
            code=diag_codes.INSERT_TARGET_EXTRACTED,
            severity=Severity.INFO,
            message="INSERT target table extracted for complex SQL cleaning.",
            stage="statement_clean",
            confidence=0.95,
            extra={"target_table": match.group("table")},
        )
    ]

    partition_match = _PARTITION_RE.search(statement.sql, pos=source_start)
    if partition_match is not None:
        open_paren = statement.sql.find("(", partition_match.start())
        close_paren = _find_matching_paren(statement.sql, open_paren)
        if close_paren > open_paren:
            source_start = close_paren + 1
            diagnostics.append(Diagnostic(
                code=diag_codes.INSERT_PARTITION_DETECTED,
                severity=Severity.INFO,
                message="INSERT partition clause extracted before source query selection.",
                stage="statement_clean",
                confidence=0.9,
            ))

    suffix = statement.sql[source_start:]
    leading = len(suffix) - len(suffix.lstrip())
    trailing = len(suffix) - len(suffix.rstrip())
    source_sql = suffix.strip()
    if not source_sql or not _QUERY_RE.match(source_sql):
        return None

    with_prefix = ""
    with_m = re.search(r"(?ims)^\s*(with\b[^;]*?)(?=\s*insert\s)", statement.sql)
    if with_m is not None:
        with_prefix = with_m.group(1).strip() + "\n"

    start_offset = statement.start_offset + source_start + leading
    end_offset = statement.end_offset - trailing
    return ScriptSelection(
        analysis_sql=with_prefix + source_sql,
        start_offset=start_offset,
        end_offset=end_offset,
        selected_target=f"insert_source_{statement.index:04d}",
        selected_kind="insert_source_query",
        statement_count=1,
        skipped_count=0,
        diagnostics=diagnostics,
    )


def _find_matching_paren(text: str, open_pos: int) -> int:
    depth = 0
    quote: str | None = None
    index = open_pos
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if quote == "'" and char == "'" and next_char == "'":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1
