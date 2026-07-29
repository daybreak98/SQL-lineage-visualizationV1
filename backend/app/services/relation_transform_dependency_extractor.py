from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlglot import exp


@dataclass(frozen=True)
class RelationTransformDependency:
    output_column: str
    source_column: str
    source_table_alias: str | None = None
    output_table_alias: str | None = None
    transform_type: str = "relation_transform"


@dataclass(frozen=True)
class PivotTransform:
    source_alias: str
    generated_columns: tuple[str, ...]
    consumed_columns: tuple[str, ...]
    dependencies: tuple[RelationTransformDependency, ...]


def extract_relation_transform_dependencies(
    tree: Any,
) -> list[RelationTransformDependency]:
    if not isinstance(tree, exp.Select):
        return []

    dependencies: list[RelationTransformDependency] = []
    dependencies.extend(_extract_unpivot_dependencies(tree))
    dependencies.extend(_extract_unnest_dependencies(tree))
    return _dedupe(dependencies)


def extract_pivot_transforms(tree: Any) -> list[PivotTransform]:
    if not isinstance(tree, exp.Select):
        return []

    transforms: list[PivotTransform] = []
    for pivot in tree.find_all(exp.Pivot):
        if pivot.find_ancestor(exp.Select) is not tree or pivot.args.get("unpivot"):
            continue
        relation = pivot.parent
        source_alias = getattr(relation, "alias_or_name", None) or ""
        if not source_alias:
            continue

        measure_columns = _column_names(pivot.expressions)
        field_columns = _column_names(pivot.args.get("fields") or [])
        consumed_columns = tuple(dict.fromkeys(measure_columns + field_columns))
        generated_columns = tuple(
            column.name
            for column in pivot.args.get("columns") or []
            if isinstance(column, exp.Identifier) and column.name
        )
        dependencies = tuple(
            RelationTransformDependency(
                output_column=output_column,
                source_column=source_column,
                source_table_alias=source_alias,
                transform_type="pivot",
            )
            for output_column in generated_columns
            for source_column in consumed_columns
        )
        transforms.append(PivotTransform(
            source_alias=source_alias,
            generated_columns=generated_columns,
            consumed_columns=consumed_columns,
            dependencies=dependencies,
        ))
    return transforms


def pivot_star_output_names(
    tree: Any,
    metadata: dict[str, list[str]] | None = None,
) -> list[str]:
    if not isinstance(tree, exp.Select) or not any(
        isinstance(item, exp.Star) for item in tree.selects
    ):
        return []
    transforms = extract_pivot_transforms(tree)
    if len(transforms) != 1:
        return []

    transform = transforms[0]
    source_columns = _pivot_source_columns(tree, transform.source_alias, metadata or {})
    consumed = {column.lower().strip("`") for column in transform.consumed_columns}
    group_columns = [
        column for column in source_columns
        if column.lower().strip("`") not in consumed
    ]
    return list(dict.fromkeys(group_columns + list(transform.generated_columns)))


def _extract_unpivot_dependencies(tree: exp.Select) -> list[RelationTransformDependency]:
    dependencies: list[RelationTransformDependency] = []
    for pivot in tree.find_all(exp.Pivot):
        if pivot.find_ancestor(exp.Select) is not tree or not pivot.args.get("unpivot"):
            continue
        relation = pivot.parent
        source_alias = getattr(relation, "alias_or_name", None) or ""
        input_columns = [
            column.name
            for field in pivot.args.get("fields") or []
            if isinstance(field, exp.In)
            for expression in field.expressions
            for column in expression.find_all(exp.Column)
            if column.name
        ]
        output_columns = [
            identifier.name
            for identifier in pivot.expressions
            if isinstance(identifier, exp.Identifier) and identifier.name
        ]
        for field in pivot.args.get("fields") or []:
            field_expression = field.this if isinstance(field, exp.In) else None
            if isinstance(field_expression, exp.Identifier) and field_expression.name:
                output_columns.append(field_expression.name)
        for output_column in dict.fromkeys(output_columns):
            for source_column in input_columns:
                dependencies.append(RelationTransformDependency(
                    output_column=output_column,
                    source_column=source_column,
                    source_table_alias=source_alias or None,
                    transform_type="unpivot",
                ))
    return dependencies


def _extract_unnest_dependencies(tree: exp.Select) -> list[RelationTransformDependency]:
    dependencies: list[RelationTransformDependency] = []
    for unnest in tree.find_all(exp.Unnest):
        if unnest.find_ancestor(exp.Select) is not tree:
            continue
        alias_expression = unnest.args.get("alias")
        output_alias = getattr(unnest, "alias_or_name", None) or ""
        output_columns = [
            column.name
            for column in getattr(alias_expression, "columns", [])
            if isinstance(column, exp.Identifier) and column.name
        ]
        source_columns = [
            column for expression in unnest.expressions
            for column in expression.find_all(exp.Column)
        ]
        for output_column in output_columns:
            for source_column in source_columns:
                dependencies.append(RelationTransformDependency(
                    output_column=output_column,
                    output_table_alias=output_alias or None,
                    source_column=source_column.name,
                    source_table_alias=source_column.table or None,
                    transform_type="unnest",
                ))
    return dependencies


def _pivot_source_columns(
    tree: exp.Select,
    source_alias: str,
    metadata: dict[str, list[str]],
) -> list[str]:
    for key in (f"subquery:{source_alias}", source_alias):
        if metadata.get(key):
            return list(metadata[key])

    for relation in tree.find_all(exp.Subquery):
        if relation.alias_or_name != source_alias or not isinstance(relation.this, exp.Query):
            continue
        return [
            projection.alias_or_name
            for projection in relation.this.selects
            if projection.alias_or_name and not isinstance(projection, exp.Star)
        ]
    return []


def _column_names(expressions: list[exp.Expression]) -> list[str]:
    return [
        column.name
        for expression in expressions
        for column in expression.find_all(exp.Column)
        if column.name
    ]


def _dedupe(
    dependencies: list[RelationTransformDependency],
) -> list[RelationTransformDependency]:
    return list(dict.fromkeys(dependencies))
