from __future__ import annotations

import time
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError as SqlglotParseError

from app.domain import diagnostics_model as diag_codes
from app.models import Diagnostic
from app.services.simple_lineage_service import SimpleColumnLineage


@dataclass(frozen=True)
class TableReference:
    table_name: str
    alias: str


@dataclass
class NameResolverResult:
    status: str
    confidence_level: str
    lineages: list[SimpleColumnLineage] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    unsupported_features: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    stage_statuses: list[dict[str, object]] = field(default_factory=list)
    alias_to_table: dict[str, str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == "success"


def resolve_column_lineage_names(sql: str, dialect: str = "spark") -> NameResolverResult:
    started = time.time()

    try:
        tree = sqlglot.parse_one(sql, dialect=dialect)
    except SqlglotParseError as exc:
        return _result(
            started=started,
            status="failed",
            confidence_level="unknown",
            diagnostics=[
                Diagnostic(
                    code=diag_codes.SQL_PARSE_ERROR,
                    level="error",
                    message=f"SQL parse error: {exc}",
                )
            ],
            stage_status="failed",
        )

    unsupported = _detect_unsupported(tree)
    if unsupported is not None:
        code, message, feature = unsupported
        return _result(
            started=started,
            status="partial",
            confidence_level="unknown",
            diagnostics=[Diagnostic(code=code, level="warning", message=message)],
            unsupported_features=[feature],
            stage_status="partial",
        )

    tables = _table_references(tree, dialect)
    if not tables:
        return _result(
            started=started,
            status="partial",
            confidence_level="unknown",
            diagnostics=[
                Diagnostic(
                    code=diag_codes.UNSUPPORTED_COMPLEX_QUERY,
                    level="warning",
                    message="C04 requires at least one physical source table.",
                )
            ],
            unsupported_features=["missing_source_table"],
            stage_status="partial",
        )

    alias_to_table = {table.alias: table.table_name for table in tables}
    table_names = {table.table_name for table in tables}
    diagnostics: list[Diagnostic] = []
    lineages: list[SimpleColumnLineage] = []

    for select_item in tree.selects:
        column = _simple_column_from_select_item(select_item)
        if column is None:
            diagnostics.append(
                Diagnostic(
                    code=diag_codes.UNSUPPORTED_COMPLEX_QUERY,
                    level="warning",
                    message="C04 only supports direct column projections, not complex expressions.",
                )
            )
            continue

        output_column = select_item.alias_or_name
        qualifier = column.table

        if qualifier:
            source_table = alias_to_table.get(qualifier)
            if source_table is None and qualifier in table_names:
                source_table = qualifier
            if source_table is None:
                diagnostics.append(
                    Diagnostic(
                        code=diag_codes.UNKNOWN_TABLE_ALIAS,
                        level="warning",
                        message=f"Table alias {qualifier} cannot be resolved from the FROM/JOIN tables.",
                    )
                )
                continue

            lineages.append(
                SimpleColumnLineage(
                    source_table=source_table,
                    source_column=column.name,
                    output_column=output_column,
                )
            )
            continue

        if len(tables) == 1:
            lineages.append(
                SimpleColumnLineage(
                    source_table=tables[0].table_name,
                    source_column=column.name,
                    output_column=output_column,
                )
            )
            continue

        diagnostics.append(
            Diagnostic(
                code=diag_codes.AMBIGUOUS_COLUMN,
                level="warning",
                message=(
                    f"Column {column.name} is not qualified. Without metadata, C04 cannot "
                    "decide which joined table owns it."
                ),
            )
        )

    status = "success" if not diagnostics else "partial"
    confidence_level = "high" if status == "success" else "unknown"
    return _result(
        started=started,
        status=status,
        confidence_level=confidence_level,
        lineages=lineages,
        diagnostics=diagnostics,
        stage_status=status,
        alias_to_table=alias_to_table,
    )


def _table_references(tree: exp.Expression, dialect: str) -> list[TableReference]:
    tables: list[TableReference] = []
    for table in tree.find_all(exp.Table):
        table_name = _table_name_without_alias(table, dialect)
        tables.append(TableReference(table_name=table_name, alias=table.alias or table.name))
    return tables


def _table_name_without_alias(table: exp.Table, dialect: str) -> str:
    parts = [part for part in [table.catalog, table.db, table.name] if part]
    if parts:
        return ".".join(parts)
    return table.sql(dialect=dialect).split(" AS ")[0]


def _simple_column_from_select_item(select_item: exp.Expression) -> exp.Column | None:
    if isinstance(select_item, exp.Column):
        return select_item
    if isinstance(select_item, exp.Alias) and isinstance(select_item.this, exp.Column):
        return select_item.this
    return None


def _detect_unsupported(tree: exp.Expression) -> tuple[str, str, str] | None:
    if tree.args.get("with") is not None:
        return (
            diag_codes.UNSUPPORTED_COMPLEX_QUERY,
            "CTE lineage is not supported in C04.",
            "cte",
        )

    if any(isinstance(node, exp.Subquery) for node in tree.find_all(exp.Subquery)):
        return (
            diag_codes.UNSUPPORTED_COMPLEX_QUERY,
            "Subquery lineage is not supported in C04.",
            "subquery",
        )

    if any(isinstance(select_item, exp.Star) for select_item in tree.selects):
        return (
            diag_codes.UNSUPPORTED_SELECT_STAR,
            "SELECT * lineage requires metadata and is not supported in C04.",
            "select_star",
        )

    return None


def _result(
    started: float,
    status: str,
    confidence_level: str,
    diagnostics: list[Diagnostic] | None = None,
    lineages: list[SimpleColumnLineage] | None = None,
    unsupported_features: list[str] | None = None,
    stage_status: str = "success",
    alias_to_table: dict[str, str] | None = None,
) -> NameResolverResult:
    elapsed = int((time.time() - started) * 1000)
    diagnostic_codes = [diagnostic.code for diagnostic in diagnostics or []]
    return NameResolverResult(
        status=status,
        confidence_level=confidence_level,
        lineages=lineages or [],
        diagnostics=diagnostics or [],
        unsupported_features=unsupported_features or [],
        elapsed_ms=elapsed,
        alias_to_table=alias_to_table or {},
        stage_statuses=[
            {
                "stage": "join_alias_resolve",
                "status": stage_status,
                "elapsed_ms": elapsed,
                "diagnostic_codes": diagnostic_codes,
                "message": "Join aliases and selected column ownership resolved.",
            }
        ],
    )
