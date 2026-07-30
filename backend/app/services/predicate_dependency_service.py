from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp

from app.domain.cte_rollup_models import (
    ColumnDependency,
    ColumnRef,
    DerivedRelationSchema,
)
from app.services.cte_column_rollup_service import CteColumnRollupService
from app.services.sqlglot_compat import get_from_expression


@dataclass(frozen=True)
class PredicateDependency:
    predicate_id: str
    predicate_kind: str
    owner_id: str
    expression: str
    root_columns: tuple[ColumnRef, ...]


@dataclass(frozen=True)
class _RelationSource:
    relation_name: str
    relation_kind: str
    alias: str


def analyze_predicate_dependencies(
    tree: exp.Expression | None,
    dialect: str = "spark",
    derived_schemas: dict[str, DerivedRelationSchema] | None = None,
) -> list[PredicateDependency]:
    if tree is None:
        return []

    schemas = derived_schemas or {}
    cte_names = {
        schema.relation_name.lower().strip("`")
        for schema in schemas.values()
        if schema.relation_kind == "cte"
    }
    if not cte_names:
        cte_names = {
            cte.alias_or_name.lower().strip("`")
            for cte in tree.find_all(exp.CTE)
            if cte.alias_or_name
        }
    subquery_ids, query_ids = _subquery_owner_ids(tree)
    rollup = CteColumnRollupService(schemas)
    counters: dict[tuple[str, str], int] = {}
    results: list[PredicateDependency] = []

    for select in tree.find_all(exp.Select):
        owner_id = _select_owner_id(select, subquery_ids, query_ids)
        for predicate_kind, condition in _select_conditions(select):
            immediate_inputs = _condition_inputs(
                condition,
                select,
                predicate_kind,
                cte_names,
                subquery_ids,
            )
            if not immediate_inputs:
                continue

            counter_key = (owner_id, predicate_kind)
            counters[counter_key] = counters.get(counter_key, 0) + 1
            predicate_id = (
                f"predicate:{predicate_kind}:{owner_id}:"
                f"{counters[counter_key]}"
            )
            dependency = ColumnDependency(
                output=ColumnRef(
                    relation_name=predicate_id,
                    column_name="condition",
                    relation_kind="output",
                ),
                inputs=immediate_inputs,
                transform_type="expression",
                expression=condition.sql(dialect=dialect),
            )
            rolled = rollup.rollup([dependency]).root_dependencies[0]
            roots = _dedupe_refs(
                root
                for root in rolled.inputs
                if root.relation_kind == "table" and root.relation_name
            )
            if not roots:
                continue
            results.append(PredicateDependency(
                predicate_id=predicate_id,
                predicate_kind=predicate_kind,
                owner_id=owner_id,
                expression=condition.sql(dialect=dialect),
                root_columns=tuple(roots),
            ))

    return results


def _select_conditions(
    select: exp.Select,
) -> list[tuple[str, exp.Expression]]:
    conditions: list[tuple[str, exp.Expression]] = []
    for join in select.args.get("joins") or []:
        on_expression = join.args.get("on")
        if isinstance(on_expression, exp.Expression):
            conditions.append(("join", on_expression))
    for argument_name, predicate_kind in (
        ("where", "where"),
        ("having", "having"),
        ("qualify", "qualify"),
    ):
        wrapper = select.args.get(argument_name)
        condition = getattr(wrapper, "this", None)
        if isinstance(condition, exp.Expression):
            conditions.append((predicate_kind, condition))
    return conditions


def _condition_inputs(
    condition: exp.Expression,
    select: exp.Select,
    predicate_kind: str,
    cte_names: set[str],
    subquery_ids: dict[int, str],
) -> list[ColumnRef]:
    inputs: list[ColumnRef] = []
    projection_aliases = {
        projection.alias_or_name.lower().strip("`"): projection
        for projection in select.expressions
        if projection.alias_or_name
    }
    for column in condition.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            continue
        if column.find_ancestor(exp.Select) is not select:
            continue
        if (
            not column.table
            and predicate_kind in {"having", "qualify"}
            and (
                alias_projection := projection_aliases.get(
                    column.name.lower().strip("`")
                )
            )
            is not None
        ):
            for source_column in alias_projection.find_all(exp.Column):
                if source_column.find_ancestor(exp.Select) is not select:
                    continue
                ref = _resolved_column_ref(
                    source_column,
                    select,
                    cte_names,
                    subquery_ids,
                )
                if ref is not None:
                    inputs.append(ref)
            continue
        ref = _resolved_column_ref(column, select, cte_names, subquery_ids)
        if ref is not None:
            inputs.append(ref)
    return _dedupe_refs(inputs)


def _resolved_column_ref(
    column: exp.Column,
    select: exp.Select,
    cte_names: set[str],
    subquery_ids: dict[int, str],
) -> ColumnRef | None:
    source = _resolve_column_source(column, select, cte_names, subquery_ids)
    if source is None or source.relation_kind == "unknown":
        return None
    return ColumnRef(
        relation_name=source.relation_name,
        column_name=column.name,
        relation_kind=source.relation_kind,
        table_alias=source.alias,
    )


def _resolve_column_source(
    column: exp.Column,
    select: exp.Select,
    cte_names: set[str],
    subquery_ids: dict[int, str],
) -> _RelationSource | None:
    qualifier = column.table.lower().strip("`") if column.table else ""
    current: exp.Select | None = select
    first_scope = True
    while current is not None:
        sources = _scope_sources(current, cte_names, subquery_ids)
        if qualifier:
            source = sources.get(qualifier)
            if source is not None:
                return source
        elif first_scope:
            unique_sources = {
                (source.relation_kind, source.relation_name): source
                for source in sources.values()
            }
            if len(unique_sources) == 1:
                return next(iter(unique_sources.values()))
            return None
        first_scope = False
        current = current.find_ancestor(exp.Select)
    return None


def _scope_sources(
    select: exp.Select,
    cte_names: set[str],
    subquery_ids: dict[int, str],
) -> dict[str, _RelationSource]:
    result: dict[str, _RelationSource] = {}
    from_expression = get_from_expression(select)
    candidates = [from_expression.this] if from_expression is not None else []
    candidates.extend(
        join.this
        for join in select.args.get("joins") or []
        if isinstance(join.this, exp.Expression)
    )
    for candidate in candidates:
        source = _relation_source(candidate, cte_names, subquery_ids)
        if source is None:
            continue
        keys = {source.alias.lower().strip("`"), source.relation_name.lower().strip("`")}
        keys.add(source.relation_name.split(".")[-1].lower().strip("`"))
        for key in keys:
            if key:
                result[key] = source
    return result


def _relation_source(
    expression: exp.Expression,
    cte_names: set[str],
    subquery_ids: dict[int, str],
) -> _RelationSource | None:
    if isinstance(expression, exp.Table):
        parts = [
            part
            for part in (expression.catalog, expression.db, expression.name)
            if part
        ]
        relation_name = ".".join(parts)
        normalized = relation_name.split(".")[-1].lower().strip("`")
        return _RelationSource(
            relation_name=relation_name,
            relation_kind="cte" if normalized in cte_names else "table",
            alias=expression.alias or expression.name,
        )
    if isinstance(expression, exp.Subquery):
        owner_id = subquery_ids.get(id(expression))
        alias = expression.alias_or_name
        if not owner_id or not alias:
            return None
        return _RelationSource(
            relation_name=owner_id.split(":", 1)[1],
            relation_kind="subquery",
            alias=alias,
        )
    return None


def _subquery_owner_ids(
    tree: exp.Expression,
) -> tuple[dict[int, str], dict[int, str]]:
    subquery_ids: dict[int, str] = {}
    query_ids: dict[int, str] = {}
    alias_counts: dict[str, int] = {}
    subqueries = list(tree.find_all(exp.Subquery))
    subqueries.sort(key=_subquery_source_offset)
    for index, subquery in enumerate(subqueries, start=1):
        alias = subquery.alias_or_name
        if not alias:
            prefix = "in_subquery" if isinstance(subquery.parent, exp.In) else "subquery"
            alias = f"{prefix}_{index}"
        alias_counts[alias] = alias_counts.get(alias, 0) + 1
        occurrence = alias_counts[alias]
        unique_alias = alias if occurrence == 1 else f"{alias}__occurrence_{occurrence}"
        subquery_ids[id(subquery)] = f"subquery:{unique_alias}"

    exists_index = 0
    for exists in tree.find_all(exp.Exists):
        query = exists.this
        if not isinstance(query, exp.Query) or isinstance(query, exp.Subquery):
            continue
        exists_index += 1
        query_ids[id(query)] = f"subquery:exists_subquery_{exists_index}"
    return subquery_ids, query_ids


def _subquery_source_offset(subquery: exp.Subquery) -> float:
    """Order subqueries by original SQL position, matching the structure graph."""
    query = subquery.this
    if isinstance(query, exp.Select):
        projection_offsets = [
            offset
            for projection in query.expressions
            if (offset := _expression_source_offset(projection)) is not None
        ]
        if projection_offsets:
            return min(projection_offsets)
    offset = _expression_source_offset(subquery)
    return float(offset) if offset is not None else float("inf")


def _expression_source_offset(
    expression: exp.Expression,
) -> int | None:
    offsets = [
        int(start)
        for node in expression.walk()
        if (start := node.meta.get("start")) is not None
    ]
    return min(offsets) if offsets else None


def _select_owner_id(
    select: exp.Select,
    subquery_ids: dict[int, str],
    query_ids: dict[int, str],
) -> str:
    direct_owner = query_ids.get(id(select))
    if direct_owner:
        return direct_owner
    parent = select.parent
    while parent is not None:
        if isinstance(parent, exp.Subquery):
            owner_id = subquery_ids.get(id(parent))
            if owner_id:
                return owner_id
        if isinstance(parent, exp.CTE) and parent.alias_or_name:
            return f"cte:{parent.alias_or_name}"
        parent = parent.parent
    return "query_result:final"


def _dedupe_refs(refs) -> list[ColumnRef]:
    result: list[ColumnRef] = []
    seen: set[tuple[str, str, str, str]] = set()
    for ref in refs:
        key = ref.lookup_key()
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result
