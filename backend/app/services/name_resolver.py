from __future__ import annotations

import time
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError as SqlglotParseError

from app.domain import diagnostics_model as diag_codes
from app.models import Diagnostic
from app.domain.lineage_model import SimpleColumnLineage
from app.services.star_expansion_service import _detect_star, expand_star_items


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


def resolve_column_lineage_names(sql: str, dialect: str = "spark",
                                  tree: exp.Expression | None = None,
                                  metadata: dict[str, list[str]] | None = None) -> NameResolverResult:
    started = time.time()

    if tree is None:
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

    unsupported = _detect_unsupported(tree, has_metadata=metadata is not None)
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
    unsupported_features: list[str] = []

    # Build metadata lookup: {table_name: set(column_names)}
    metadata_cols: dict[str, set[str]] = {}
    if metadata:
        metadata_cols = {tname: set(cols) for tname, cols in metadata.items()}

    # -- Handle SELECT * via star_expansion_service --
    if metadata and _has_any_star(tree.selects):
        source_table_names = list(table_names)
        columns_by_table = {tname: [{"name": c} for c in cols] for tname, cols in (metadata or {}).items()}
        star_result = expand_star_items(tree.selects, source_table_names, alias_to_table, columns_by_table)
        lineages.extend(star_result.lineages)
        diagnostics.extend(star_result.diagnostics)
        unsupported_features.extend(star_result.unsupported_features)

    for select_item in tree.selects:
        is_star, _qualifier = _detect_star(select_item)
        if is_star:
            continue  # handled above

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

            # Metadata validation: column exists? (only when metadata is non-empty)
            cols_for_table = metadata_cols.get(source_table)
            if cols_for_table and column.name not in cols_for_table:
                diagnostics.append(
                    Diagnostic(
                        code=diag_codes.UNKNOWN_COLUMN,
                        level="warning",
                        message=f"Column {column.name} not found in table {source_table} metadata.",
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

        # Unqualified column
        if len(tables) == 1:
            source_table = tables[0].table_name
            cols_for_table = metadata_cols.get(source_table)
            if cols_for_table and column.name not in cols_for_table:
                diagnostics.append(
                    Diagnostic(
                        code=diag_codes.UNKNOWN_COLUMN,
                        level="warning",
                        message=f"Column {column.name} not found in table {source_table} metadata.",
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

        # Unqualified + multiple tables: try metadata disambiguation
        tables_with_meta = [t for t in tables if metadata_cols.get(t.table_name)]
        tables_without_meta = [t for t in tables if not metadata_cols.get(t.table_name)]

        # Cannot auto-disambiguate when not all source tables have metadata
        if tables_without_meta:
            diagnostics.append(
                Diagnostic(
                    code=diag_codes.AMBIGUOUS_COLUMN,
                    level="warning",
                    message=(
                        f"Column {column.name} is not qualified. Metadata missing for: "
                        f"{', '.join(t.table_name for t in tables_without_meta)}. "
                        f"Cannot determine ownership. Qualify with table alias."
                    ),
                )
            )
            continue

        # All tables have metadata → safe disambiguation
        candidates = [t for t in tables if column.name in metadata_cols[t.table_name]]
        if len(candidates) == 1:
            lineages.append(
                SimpleColumnLineage(
                    source_table=candidates[0].table_name,
                    source_column=column.name,
                    output_column=output_column,
                )
            )
            continue

        if len(candidates) > 1:
            diagnostics.append(
                Diagnostic(
                    code=diag_codes.AMBIGUOUS_COLUMN,
                    level="warning",
                    message=(
                        f"Column {column.name} exists in multiple tables: "
                        f"{', '.join(t.table_name for t in candidates)}. Qualify with table alias."
                    ),
                )
            )
            continue

        # candidates == 0 + all metadata loaded → column truly unknown
        diagnostics.append(
            Diagnostic(
                code=diag_codes.UNKNOWN_COLUMN,
                level="warning",
                message=(
                    f"Column {column.name} not found in metadata for any source table: "
                    f"{', '.join(t.table_name for t in tables)}."
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
        unsupported_features=unsupported_features,
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


def _detect_unsupported(tree: exp.Expression, has_metadata: bool = False) -> tuple[str, str, str] | None:
    if tree.args.get("with_") is not None:
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

    if _has_any_star(tree.selects):
        if has_metadata:
            return None  # C07: let star_expansion_service handle it
        return (
            diag_codes.SELECT_STAR_METADATA_REQUIRED,
            "SELECT * requires table metadata. Import metadata or qualify columns explicitly.",
            "select_star",
        )

    return None


def _has_any_star(select_items: list[exp.Expression]) -> bool:
    return any(_detect_star(item)[0] for item in select_items)


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
