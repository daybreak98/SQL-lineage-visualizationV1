from __future__ import annotations

import time
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError as SqlglotParseError

from app.domain import diagnostics_model as diag_codes
from app.domain.lineage_context import LineageResolveContext
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
                                  metadata: dict[str, list[str]] | None = None,
                                  is_cte_context: bool = False,
                                  context: LineageResolveContext | None = None) -> NameResolverResult:
    # Derive scope from context (takes precedence over is_cte_context)
    if context is not None:
        is_cte_context = context.has_cte or context.allow_cte
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

    unsupported = _detect_unsupported(
        tree, has_metadata=metadata is not None,
        is_cte_context=is_cte_context, context=context)
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

    tables = _table_references(tree, dialect, is_cte_context=is_cte_context, context=context)
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
            expression_lineages, expression_diagnostics = _expression_column_lineages(
                select_item=select_item,
                tables=tables,
                alias_to_table=alias_to_table,
                metadata_cols=metadata_cols,
            )
            lineages.extend(expression_lineages)
            diagnostics.extend(expression_diagnostics)
            if not expression_lineages and not expression_diagnostics:
                diagnostics.append(
                    Diagnostic(
                        code=diag_codes.UNSUPPORTED_COMPLEX_QUERY,
                        level="warning",
                        message=(
                            "Expression projection has no resolvable source columns. "
                            "Only source-column dependency extraction is supported."
                        ),
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


def _table_references(tree: exp.Expression, dialect: str,
                       is_cte_context: bool = False,
                       context: LineageResolveContext | None = None) -> list[TableReference]:
    if is_cte_context or (context is not None and context.has_cte):
        return _table_references_from_final_select(tree, dialect)
    tables: list[TableReference] = []
    for table in tree.find_all(exp.Table):
        table_name = _table_name_without_alias(table, dialect)
        tables.append(TableReference(table_name=table_name, alias=table.alias or table.name))
    return tables


def _table_references_from_final_select(tree: exp.Expression, dialect: str) -> list[TableReference]:
    tables: list[TableReference] = []
    from_expr = tree.args.get("from_")
    _extract_table_or_subquery(from_expr, tables, dialect)
    for join in tree.args.get("joins") or []:
        _extract_table_or_subquery(join, tables, dialect)
    return tables


def _extract_table_or_subquery(node, tables: list[TableReference], dialect: str) -> None:
    if node is None:
        return
    target = getattr(node, "this", node)
    if isinstance(target, exp.Table):
        table_name = _table_name_without_alias(target, dialect)
        tables.append(TableReference(table_name=table_name, alias=target.alias or target.name))
    elif isinstance(target, exp.Subquery):
        alias = getattr(node, "alias_or_name", None) or getattr(target, "alias_or_name", None)
        if alias:
            tables.append(TableReference(table_name=f"subquery:{alias}", alias=alias))


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


def _expression_column_lineages(
    select_item: exp.Expression,
    tables: list[TableReference],
    alias_to_table: dict[str, str],
    metadata_cols: dict[str, set[str]],
) -> tuple[list[SimpleColumnLineage], list[Diagnostic]]:
    output_column = select_item.alias_or_name
    source_columns = _source_columns_in_expression(select_item)
    lineages: list[SimpleColumnLineage] = []
    diagnostics: list[Diagnostic] = []
    seen_lineages: set[tuple[str, str, str]] = set()

    for column in source_columns:
        source_table, diagnostic = _resolve_source_table_for_column(
            column=column,
            tables=tables,
            alias_to_table=alias_to_table,
            metadata_cols=metadata_cols,
        )
        if diagnostic is not None:
            diagnostics.append(diagnostic)
            continue
        if source_table is None:
            continue

        key = (source_table, column.name, output_column)
        if key in seen_lineages:
            continue
        seen_lineages.add(key)
        lineages.append(
            SimpleColumnLineage(
                source_table=source_table,
                source_column=column.name,
                output_column=output_column,
            )
        )

    return lineages, diagnostics


def _source_columns_in_expression(select_item: exp.Expression) -> list[exp.Column]:
    expression = select_item.this if isinstance(select_item, exp.Alias) else select_item
    columns: list[exp.Column] = []
    seen: set[tuple[str, str]] = set()

    for column in expression.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            continue
        key = (column.table, column.name)
        if key in seen:
            continue
        seen.add(key)
        columns.append(column)

    return columns


def _resolve_source_table_for_column(
    column: exp.Column,
    tables: list[TableReference],
    alias_to_table: dict[str, str],
    metadata_cols: dict[str, set[str]],
) -> tuple[str | None, Diagnostic | None]:
    table_names = {table.table_name for table in tables}
    qualifier = column.table

    if qualifier:
        source_table = alias_to_table.get(qualifier)
        if source_table is None and qualifier in table_names:
            source_table = qualifier
        if source_table is None:
            return None, Diagnostic(
                code=diag_codes.UNKNOWN_TABLE_ALIAS,
                level="warning",
                message=f"Table alias {qualifier} cannot be resolved from the FROM/JOIN tables.",
            )

        cols_for_table = metadata_cols.get(source_table)
        if cols_for_table and column.name not in cols_for_table:
            return None, Diagnostic(
                code=diag_codes.UNKNOWN_COLUMN,
                level="warning",
                message=f"Column {column.name} not found in table {source_table} metadata.",
            )
        return source_table, None

    if len(tables) == 1:
        source_table = tables[0].table_name
        cols_for_table = metadata_cols.get(source_table)
        if cols_for_table and column.name not in cols_for_table:
            return None, Diagnostic(
                code=diag_codes.UNKNOWN_COLUMN,
                level="warning",
                message=f"Column {column.name} not found in table {source_table} metadata.",
            )
        return source_table, None

    tables_without_meta = [table for table in tables if not metadata_cols.get(table.table_name)]
    if tables_without_meta:
        return None, Diagnostic(
            code=diag_codes.AMBIGUOUS_COLUMN,
            level="warning",
            message=(
                f"Column {column.name} is not qualified. Metadata missing for: "
                f"{', '.join(table.table_name for table in tables_without_meta)}. "
                f"Cannot determine ownership. Qualify with table alias."
            ),
        )

    candidates = [table for table in tables if column.name in metadata_cols[table.table_name]]
    if len(candidates) == 1:
        return candidates[0].table_name, None
    if len(candidates) > 1:
        return None, Diagnostic(
            code=diag_codes.AMBIGUOUS_COLUMN,
            level="warning",
            message=(
                f"Column {column.name} exists in multiple tables: "
                f"{', '.join(table.table_name for table in candidates)}. Qualify with table alias."
            ),
        )

    return None, Diagnostic(
        code=diag_codes.UNKNOWN_COLUMN,
        level="warning",
        message=(
            f"Column {column.name} not found in metadata for any source table: "
            f"{', '.join(table.table_name for table in tables)}."
        ),
    )


def _detect_unsupported(tree: exp.Expression, has_metadata: bool = False,
                         is_cte_context: bool = False,
                         context: LineageResolveContext | None = None) -> tuple[str, str, str] | None:
    skip_cte_check = is_cte_context or (context is not None and (context.allow_cte or context.has_cte))
    skip_subq_check = is_cte_context or (context is not None and context.allow_subquery)

    if not skip_cte_check:
        if tree.args.get("with_") is not None:
            return (
                diag_codes.UNSUPPORTED_COMPLEX_QUERY,
                "CTE lineage is not supported in C04.",
                "cte",
            )

    if not skip_subq_check:
        if any(isinstance(node, exp.Subquery) for node in tree.find_all(exp.Subquery)):
            return (
                diag_codes.UNSUPPORTED_COMPLEX_QUERY,
                "Subquery lineage is not supported in C04.",
                "subquery",
            )

    has_lateral = any(isinstance(node, exp.Lateral) for node in tree.find_all(exp.Lateral))
    if has_lateral and not skip_subq_check:
        return (
            diag_codes.UNSUPPORTED_LATERAL_VIEW,
            "lateral view / explode lineage is not supported in the current name resolver.",
            "lateral_view",
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
