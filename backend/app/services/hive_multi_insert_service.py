from __future__ import annotations

from sqlglot import Dialect, exp, parse_one
from sqlglot.errors import ParseError, TokenError

from app.models import OutputField
from app.services.dml_projection_service import DmlProjectionResult


_BRANCH_CLAUSES = {
    "WHERE",
    "GROUP_BY",
    "HAVING",
    "QUALIFY",
    "WINDOW",
    "ORDER_BY",
    "CLUSTER_BY",
    "DISTRIBUTE_BY",
    "SORT_BY",
    "LIMIT",
}


def build_hive_multi_insert_projection(
    sql: str,
    dialect: str = "hive",
) -> DmlProjectionResult | None:
    """Normalize Hive's FROM-first multi-insert syntax for lineage analysis.

    Each write branch becomes a derived query so its predicates and nested
    subqueries remain visible. The final synthetic projection gives every
    output a target-qualified name, preventing fields from different target
    tables from collapsing into a single output node.
    """
    try:
        tokens = Dialect.get_or_raise(dialect).tokenizer().tokenize(sql)
    except (ValueError, ParseError, TokenError):
        return None

    top_level = _top_level_tokens(tokens)
    inserts = [token for token in top_level if token.token_type.name == "INSERT"]
    if len(inserts) < 2:
        return None

    first_insert = inserts[0]
    source_from = next(
        (
            token
            for token in top_level
            if token.token_type.name == "FROM" and token.start < first_insert.start
        ),
        None,
    )
    if source_from is None:
        return None

    common_prefix = sql[: source_from.start]
    common_from = sql[source_from.start : first_insert.start].strip()
    if not common_from:
        return None

    branch_queries: list[exp.Select] = []
    target_names: list[str] = []
    target_columns_by_branch: list[list[str]] = []
    for index, insert_token in enumerate(inserts):
        branch_end = inserts[index + 1].start if index + 1 < len(inserts) else len(sql)
        branch_tokens = [
            token
            for token in top_level
            if insert_token.start <= token.start < branch_end
        ]
        select_token = next(
            (token for token in branch_tokens if token.token_type.name == "SELECT"),
            None,
        )
        if select_token is None:
            return None

        target = _parse_insert_target(
            sql[insert_token.start : select_token.start],
            dialect,
        )
        if target is None:
            return None
        target_name, target_columns = target

        clause_token = next(
            (
                token
                for token in branch_tokens
                if token.start > select_token.start
                and token.token_type.name in _BRANCH_CLAUSES
            ),
            None,
        )
        projection_end = clause_token.start if clause_token is not None else branch_end
        branch_select = sql[select_token.start : projection_end].strip()
        branch_tail = sql[projection_end:branch_end].strip()
        branch_sql = "\n".join(
            part
            for part in (common_prefix.strip(), branch_select, common_from, branch_tail)
            if part
        )
        try:
            query = parse_one(branch_sql, read=dialect)
        except ParseError:
            return None
        if not isinstance(query, exp.Select):
            return None

        projections = list(query.expressions)
        if target_columns and len(target_columns) != len(projections):
            return None
        if not target_columns:
            target_columns = [_projection_name(projection, dialect) for projection in projections]
            if any(not name or name == "*" for name in target_columns):
                return None

        branch_queries.append(query)
        target_names.append(target_name)
        target_columns_by_branch.append(target_columns)

    return _compose_multi_insert_projection(
        branch_queries,
        target_names,
        target_columns_by_branch,
        dialect,
    )


def _top_level_tokens(tokens: list) -> list:
    result: list = []
    depth = 0
    for token in tokens:
        token_type = token.token_type.name
        if token_type == "R_PAREN":
            depth = max(0, depth - 1)
        if depth == 0:
            result.append(token)
        if token_type == "L_PAREN":
            depth += 1
    return result


def _parse_insert_target(
    header: str,
    dialect: str,
) -> tuple[str, list[str]] | None:
    try:
        statement = parse_one(f"{header} SELECT 1", read=dialect)
    except ParseError:
        return None
    if not isinstance(statement, exp.Insert):
        return None

    target = statement.this
    target_columns: list[str] = []
    if isinstance(target, exp.Schema):
        target_columns = [item.name for item in target.expressions if item.name]
        target = target.this
    if not isinstance(target, exp.Table):
        return None

    parts = [part for part in (target.catalog, target.db, target.name) if part]
    target_name = ".".join(parts)
    return (target_name, target_columns) if target_name else None


def _projection_name(projection: exp.Expression, dialect: str) -> str:
    name = projection.alias_or_name or getattr(projection, "output_name", "")
    return name or projection.sql(dialect=dialect)


def _compose_multi_insert_projection(
    branch_queries: list[exp.Select],
    target_names: list[str],
    target_columns_by_branch: list[list[str]],
    dialect: str,
) -> DmlProjectionResult:
    branch_subqueries: list[exp.Subquery] = []
    final_projections: list[exp.Expression] = []
    output_fields: list[OutputField] = []
    shared_with = branch_queries[0].args.get("with_")
    for query in branch_queries:
        query.set("with_", None)

    for branch_index, (query, target_name, target_columns) in enumerate(
        zip(branch_queries, target_names, target_columns_by_branch),
        start=1,
    ):
        branch_alias = f"__dml_branch_{branch_index}"
        internal_projections: list[exp.Expression] = []
        for column_index, (projection, target_column) in enumerate(
            zip(query.expressions, target_columns),
            start=1,
        ):
            internal_name = f"__dml_col_{branch_index}_{column_index}"
            internal_projections.append(projection.copy().as_(internal_name, quoted=False))
            output_name = f"{target_name}.{target_column}"
            final_projections.append(
                exp.column(internal_name, table=branch_alias).as_(output_name, quoted=True)
            )
            output_fields.append(OutputField(
                name=output_name,
                display_name=output_name,
                expression=projection.sql(dialect=dialect),
                source_type="expression",
            ))
        query.set("expressions", internal_projections)
        branch_subqueries.append(query.subquery(branch_alias))

    final_tree = exp.select(*final_projections).from_(branch_subqueries[0])
    for branch in branch_subqueries[1:]:
        final_tree = final_tree.join(branch, join_type="CROSS")
    if shared_with is not None:
        final_tree.set("with_", shared_with.copy())
    return DmlProjectionResult(tree=final_tree, output_fields=output_fields)
