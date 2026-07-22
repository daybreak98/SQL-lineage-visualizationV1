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
from app.services.lateral_view_dependency_extractor import extract_lateral_view_dependencies
from app.services.star_expansion_service import _detect_star, expand_star_items
from app.services.sqlglot_compat import (
    get_from_expression,
    get_with_expression,
    is_set_operation,
)


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

    if is_set_operation(tree):
        return _resolve_set_operation_lineages(
            tree=tree,
            dialect=dialect,
            metadata=metadata,
            context=context,
            started=started,
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
    lateral_by_output: dict[str, list] = {}
    for dependency in extract_lateral_view_dependencies(tree):
        lateral_by_output.setdefault(
            dependency.output_column.lower().strip("`"), []
        ).append(dependency)
    if lateral_by_output:
        diagnostics.append(Diagnostic(
            code=diag_codes.UNSUPPORTED_LATERAL_VIEW,
            level="warning",
            message=(
                "LATERAL VIEW column dependencies were extracted with medium confidence; "
                "row-expansion semantics remain defensive."
            ),
        ))
        unsupported_features.append("lateral_view")

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
        lateral_sources = (
            lateral_by_output.get(column.name.lower().strip("`"), [])
            if column is not None
            else []
        )
        if lateral_sources:
            output_column = select_item.alias_or_name
            for dependency in lateral_sources:
                source_table = alias_to_table.get(dependency.source_table_alias or "")
                if source_table is None and len(tables) == 1:
                    source_table = tables[0].table_name
                if source_table is None:
                    diagnostics.append(Diagnostic(
                        code=diag_codes.UNKNOWN_TABLE_ALIAS,
                        level="warning",
                        message=(
                            "LATERAL VIEW source alias "
                            f"{dependency.source_table_alias or '<unknown>'} cannot be resolved."
                        ),
                    ))
                    continue
                lineages.append(SimpleColumnLineage(
                    source_table=source_table,
                    source_column=dependency.source_column,
                    output_column=output_column,
                ))
            continue
        if column is None:
            expression_lineages, expression_diagnostics = _expression_column_lineages(
                select_item=select_item,
                outer_tables=tables,
                metadata_cols=metadata_cols,
                dialect=dialect,
            )
            lineages.extend(expression_lineages)
            diagnostics.extend(expression_diagnostics)
            if not expression_lineages and not expression_diagnostics:
                if (
                    _source_columns_in_expression(select_item)
                    or select_item.find(exp.Star) is not None
                ):
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
        physical_tables = [t for t in tables if not t.table_name.startswith("subquery:")]
        if len(physical_tables) == 1:
            source_table = physical_tables[0].table_name
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
    if not (context is not None and context.allow_subquery):
        lineages = _resolve_subquery_lineages_to_physical(lineages, tree, dialect)
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


def _resolve_set_operation_lineages(
    tree: exp.Expression,
    dialect: str,
    metadata: dict[str, list[str]] | None,
    context: LineageResolveContext | None,
    started: float,
) -> NameResolverResult:
    branches = _set_operation_selects(tree)
    if not branches:
        return _result(
            started=started,
            status="partial",
            confidence_level="unknown",
            diagnostics=[Diagnostic(
                code=diag_codes.UNSUPPORTED_COMPLEX_QUERY,
                level="warning",
                message="Set operation has no resolvable SELECT branches.",
            )],
            unsupported_features=["set_operation"],
            stage_status="partial",
        )

    canonical_outputs = [
        projection.alias_or_name or f"_col_{index + 1}"
        for index, projection in enumerate(branches[0].selects)
    ]
    lineages: list[SimpleColumnLineage] = []
    diagnostics: list[Diagnostic] = []
    unsupported_features: list[str] = []
    alias_to_table: dict[str, str] = {}
    statuses: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    for branch in branches:
        branch_result = resolve_column_lineage_names(
            branch.sql(dialect=dialect),
            dialect,
            tree=branch,
            metadata=metadata,
            context=context,
        )
        statuses.append(branch_result.status)
        diagnostics.extend(branch_result.diagnostics)
        unsupported_features.extend(branch_result.unsupported_features)
        alias_to_table.update(branch_result.alias_to_table)

        branch_outputs = [
            projection.alias_or_name or f"_col_{index + 1}"
            for index, projection in enumerate(branch.selects)
        ]
        output_positions = {
            output.lower().strip("`"): index
            for index, output in enumerate(branch_outputs)
        }
        for lineage in branch_result.lineages:
            index = output_positions.get(lineage.output_column.lower().strip("`"))
            if index is None or index >= len(canonical_outputs):
                diagnostics.append(Diagnostic(
                    code=diag_codes.UNSUPPORTED_COMPLEX_QUERY,
                    level="warning",
                    message=(
                        f"Set-operation output {lineage.output_column} cannot be mapped "
                        "to the first branch by position."
                    ),
                ))
                continue
            mapped = SimpleColumnLineage(
                source_table=lineage.source_table,
                source_column=lineage.source_column,
                output_column=canonical_outputs[index],
            )
            key = (mapped.source_table, mapped.source_column, mapped.output_column)
            if key not in seen:
                seen.add(key)
                lineages.append(mapped)

    status = "failed" if statuses and all(item == "failed" for item in statuses) else (
        "partial" if diagnostics or any(item != "success" for item in statuses) else "success"
    )
    return _result(
        started=started,
        status=status,
        confidence_level="high" if status == "success" else "unknown",
        lineages=lineages,
        diagnostics=diagnostics,
        unsupported_features=list(dict.fromkeys(unsupported_features)),
        stage_status=status,
        alias_to_table=alias_to_table,
    )


def _set_operation_selects(tree: exp.Expression) -> list[exp.Select]:
    if is_set_operation(tree):
        return _set_operation_selects(tree.this) + _set_operation_selects(tree.expression)
    if isinstance(tree, exp.Subquery):
        return _set_operation_selects(tree.this)
    return [tree] if isinstance(tree, exp.Select) else []


def _table_references(tree: exp.Expression, dialect: str,
                       is_cte_context: bool = False,
                       context: LineageResolveContext | None = None) -> list[TableReference]:
    if (
        is_cte_context
        or (
            context is not None
            and (context.has_cte or context.allow_cte or context.allow_subquery)
        )
    ):
        cte_names = set(context.cte_names) if context else set()
        return _table_references_from_final_select(tree, dialect, cte_names)
    tables: list[TableReference] = []
    for table in tree.find_all(exp.Table):
        table_name = _table_name_without_alias(table, dialect)
        tables.append(TableReference(table_name=table_name, alias=table.alias or table.name))
    return tables


def _table_references_from_final_select(tree: exp.Expression, dialect: str,
                                         cte_names: set[str] | None = None) -> list[TableReference]:
    cte_names = cte_names or set()
    tables: list[TableReference] = []
    from_expr = get_from_expression(tree)
    _extract_table_or_subquery(from_expr, tables, dialect, cte_names)
    for join in tree.args.get("joins") or []:
        _extract_table_or_subquery(join, tables, dialect, cte_names)
    return tables


def _extract_table_or_subquery(node, tables: list[TableReference], dialect: str,
                                 cte_names: set[str] | None = None) -> None:
    cte_names = cte_names or set()
    if node is None:
        return
    target = getattr(node, "this", node)
    if isinstance(target, exp.Table):
        table_name = _table_name_without_alias(target, dialect)
        alias = target.alias or target.name
        if alias in cte_names or table_name.split(".")[-1] in cte_names:
            tables.append(TableReference(table_name=table_name.split(".")[-1], alias=alias))
            return
        tables.append(TableReference(table_name=table_name, alias=alias))
    elif isinstance(target, exp.Subquery):
        alias = getattr(node, "alias_or_name", None) or getattr(target, "alias_or_name", None)
        if alias:
            tables.append(TableReference(table_name=f"subquery:{alias}", alias=alias))


def _resolve_subquery_lineages_to_physical(
    lineages: list[SimpleColumnLineage],
    tree: exp.Expression | None,
    dialect: str,
) -> list[SimpleColumnLineage]:
    if tree is None:
        return lineages
    subq_map: dict[str, str] = {}
    for join in tree.args.get("joins") or []:
        from_expr = get_from_expression(tree)
        for expr in ([from_expr] if from_expr else []) + list(tree.args.get("joins") or []):
            if expr is None:
                continue
            target = getattr(expr, "this", expr)
            if isinstance(target, exp.Subquery):
                alias = getattr(expr, "alias_or_name", None) or getattr(target, "alias_or_name", None)
                if alias:
                    tables = set()
                    for t in target.find_all(exp.Table):
                        parts = [p for p in [t.catalog, t.db, t.name] if p]
                        name = ".".join(parts) if parts else t.name
                        tables.add(name)
                    if len(tables) == 1:
                        subq_map[alias] = list(tables)[0]
    resolved: list[SimpleColumnLineage] = []
    for lineage in lineages:
        st = lineage.source_table
        if st.startswith("subquery:"):
            subq_alias = st[len("subquery:"):]
            if subq_alias in subq_map:
                st = subq_map[subq_alias]
        resolved.append(SimpleColumnLineage(
            source_table=st,
            source_column=lineage.source_column,
            output_column=lineage.output_column,
        ))
    return resolved

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
    outer_tables: list[TableReference],
    metadata_cols: dict[str, set[str]],
    dialect: str,
) -> tuple[list[SimpleColumnLineage], list[Diagnostic]]:
    output_column = select_item.alias_or_name
    source_columns = _source_columns_in_expression(select_item)
    lineages: list[SimpleColumnLineage] = []
    diagnostics: list[Diagnostic] = []
    seen_lineages: set[tuple[str, str, str]] = set()

    for column in source_columns:
        table_scopes = _table_scopes_for_column(
            column=column,
            select_item=select_item,
            outer_tables=outer_tables,
            dialect=dialect,
        )
        source_table, diagnostic = _resolve_source_table_for_column_scopes(
            column=column,
            table_scopes=table_scopes,
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
    seen: set[tuple[int, str, str]] = set()

    for column in expression.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            continue
        owner_select = column.find_ancestor(exp.Select)
        key = (id(owner_select), column.table, column.name)
        if key in seen:
            continue
        seen.add(key)
        columns.append(column)

    return columns


def _table_scopes_for_column(
    column: exp.Column,
    select_item: exp.Expression,
    outer_tables: list[TableReference],
    dialect: str,
) -> list[list[TableReference]]:
    projection_select = select_item.find_ancestor(exp.Select)
    current_select = column.find_ancestor(exp.Select)
    scopes: list[list[TableReference]] = []
    seen_scopes: set[tuple[tuple[str, str], ...]] = set()

    while current_select is not None and current_select is not projection_select:
        scope = _table_references_from_final_select(current_select, dialect)
        _append_table_scope(scopes, seen_scopes, scope)
        current_select = current_select.find_ancestor(exp.Select)

    _append_table_scope(scopes, seen_scopes, outer_tables)
    return scopes


def _append_table_scope(
    scopes: list[list[TableReference]],
    seen_scopes: set[tuple[tuple[str, str], ...]],
    scope: list[TableReference],
) -> None:
    if not scope:
        return
    identity = tuple((table.table_name, table.alias) for table in scope)
    if identity in seen_scopes:
        return
    seen_scopes.add(identity)
    scopes.append(scope)


def _resolve_source_table_for_column_scopes(
    column: exp.Column,
    table_scopes: list[list[TableReference]],
    metadata_cols: dict[str, set[str]],
) -> tuple[str | None, Diagnostic | None]:
    if not table_scopes:
        return None, None

    if not column.table:
        scope = table_scopes[0]
        return _resolve_source_table_for_column(
            column=column,
            tables=scope,
            alias_to_table={table.alias: table.table_name for table in scope},
            metadata_cols=metadata_cols,
        )

    qualifier = column.table
    for scope in table_scopes:
        alias_to_table = {table.alias: table.table_name for table in scope}
        table_names = {table.table_name for table in scope}
        if qualifier not in alias_to_table and qualifier not in table_names:
            continue
        return _resolve_source_table_for_column(
            column=column,
            tables=scope,
            alias_to_table=alias_to_table,
            metadata_cols=metadata_cols,
        )

    return None, Diagnostic(
        code=diag_codes.UNKNOWN_TABLE_ALIAS,
        level="warning",
        message=f"Table alias {qualifier} cannot be resolved from the FROM/JOIN tables.",
    )


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

    physical_tables = [t for t in tables if not t.table_name.startswith("subquery:")]
    if len(physical_tables) == 1:
        source_table = physical_tables[0].table_name
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
        if get_with_expression(tree) is not None:
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
    if has_lateral and not extract_lateral_view_dependencies(tree):
        return (
            diag_codes.UNSUPPORTED_LATERAL_VIEW,
            "lateral view / explode output cannot be resolved to an input column.",
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
