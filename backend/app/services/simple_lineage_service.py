from __future__ import annotations

import time
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError as SqlglotParseError

from app.models import Diagnostic


@dataclass(frozen=True)
class SimpleColumnLineage:
    source_table: str
    source_column: str
    output_column: str

    @property
    def source_label(self) -> str:
        return f"{self.source_table}.{self.source_column}"


@dataclass
class SimpleLineageResult:
    status: str
    confidence_level: str
    lineages: list[SimpleColumnLineage] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    unsupported_features: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    stage_statuses: list[dict[str, object]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.status == "success"


def analyze_simple_column_lineage(sql: str, dialect: str = "spark") -> SimpleLineageResult:
    started = time.time()

    try:
        tree = sqlglot.parse_one(sql, dialect=dialect)
    except SqlglotParseError as exc:
        return _failed(
            started,
            "SQL_PARSE_ERROR",
            f"SQL parse error: {exc}",
        )

    unsupported = _detect_unsupported(tree)
    if unsupported is not None:
        code, message, feature = unsupported
        return _partial(started, code, message, feature)

    table = _single_source_table(tree)
    if table is None:
        return _partial(
            started,
            "UNSUPPORTED_COMPLEX_QUERY",
            "C03 only supports SELECT statements with exactly one physical source table.",
            "complex_query",
        )

    table_name = table.sql(dialect=dialect)
    lineages: list[SimpleColumnLineage] = []

    for select_item in tree.selects:
        column = _simple_column_from_select_item(select_item)
        if column is None:
            return _partial(
                started,
                "UNSUPPORTED_COMPLEX_QUERY",
                "C03 only supports direct column projections such as a, t.a, or a AS aa.",
                "complex_expression",
            )

        if column.table and column.table not in {table.name, table_name}:
            return _partial(
                started,
                "UNSUPPORTED_COMPLEX_QUERY",
                f"Column qualifier {column.table} does not match the single source table {table_name}.",
                "table_alias_or_qualifier",
            )

        output_column = select_item.alias_or_name
        lineages.append(
            SimpleColumnLineage(
                source_table=table_name,
                source_column=column.name,
                output_column=output_column,
            )
        )

    elapsed = _elapsed_ms(started)
    return SimpleLineageResult(
        status="success",
        confidence_level="high",
        lineages=lineages,
        elapsed_ms=elapsed,
        stage_statuses=[
            {
                "stage": "single_table_lineage",
                "status": "success",
                "elapsed_ms": elapsed,
                "diagnostic_codes": [],
                "message": "Single-table column lineage extracted.",
            }
        ],
    )


def _detect_unsupported(tree: exp.Expression) -> tuple[str, str, str] | None:
    if tree.args.get("with") is not None:
        return (
            "UNSUPPORTED_COMPLEX_QUERY",
            "CTE lineage is not supported in C03.",
            "cte",
        )

    if tree.args.get("joins"):
        return (
            "UNSUPPORTED_COMPLEX_QUERY",
            "Join lineage is not supported in C03.",
            "join",
        )

    if any(isinstance(node, exp.Subquery) for node in tree.find_all(exp.Subquery)):
        return (
            "UNSUPPORTED_COMPLEX_QUERY",
            "Subquery lineage is not supported in C03.",
            "subquery",
        )

    if any(isinstance(select_item, exp.Star) for select_item in tree.selects):
        return (
            "UNSUPPORTED_SELECT_STAR",
            "SELECT * lineage requires metadata and is not supported in C03.",
            "select_star",
        )

    return None


def _single_source_table(tree: exp.Expression) -> exp.Table | None:
    from_expr = tree.args.get("from")
    if from_expr is None or not isinstance(from_expr.this, exp.Table):
        return None

    tables = list(tree.find_all(exp.Table))
    if len(tables) != 1:
        return None

    return tables[0]


def _simple_column_from_select_item(select_item: exp.Expression) -> exp.Column | None:
    if isinstance(select_item, exp.Column):
        return select_item

    if isinstance(select_item, exp.Alias) and isinstance(select_item.this, exp.Column):
        return select_item.this

    return None


def _partial(
    started: float,
    code: str,
    message: str,
    feature: str,
) -> SimpleLineageResult:
    elapsed = _elapsed_ms(started)
    return SimpleLineageResult(
        status="partial",
        confidence_level="unknown",
        diagnostics=[Diagnostic(code=code, level="warning", message=message)],
        unsupported_features=[feature],
        elapsed_ms=elapsed,
        stage_statuses=[
            {
                "stage": "single_table_lineage",
                "status": "partial",
                "elapsed_ms": elapsed,
                "diagnostic_codes": [code],
                "message": message,
            }
        ],
    )


def _failed(started: float, code: str, message: str) -> SimpleLineageResult:
    elapsed = _elapsed_ms(started)
    return SimpleLineageResult(
        status="failed",
        confidence_level="unknown",
        diagnostics=[Diagnostic(code=code, level="error", message=message)],
        elapsed_ms=elapsed,
        stage_statuses=[
            {
                "stage": "single_table_lineage",
                "status": "failed",
                "elapsed_ms": elapsed,
                "diagnostic_codes": [code],
                "message": message,
            }
        ],
    )


def _elapsed_ms(started: float) -> int:
    return int((time.time() - started) * 1000)
