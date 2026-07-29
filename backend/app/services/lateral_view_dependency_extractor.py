from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlglot import exp


@dataclass
class LateralViewDependency:
    output_alias: str
    output_column: str
    source_column: str | None
    source_table_alias: str | None = None
    transform: str = ""
    confidence: str = "medium"


def extract_lateral_view_dependencies(tree: Any) -> list[LateralViewDependency]:
    if tree is None:
        return []
    deps: list[LateralViewDependency] = []
    seen: set[tuple[str, str, str, str]] = set()
    for lateral in tree.find_all(exp.Lateral):
        if isinstance(tree, exp.Select) and lateral.find_ancestor(exp.Select) is not tree:
            continue
        alias_expression = lateral.args.get("alias")
        output_alias = getattr(lateral, "alias_or_name", None) or ""
        output_columns = [
            column.name if isinstance(column, exp.Identifier) else str(column)
            for column in getattr(alias_expression, "columns", [])
        ]
        source_groups = _positional_source_groups(
            lateral.this,
            len(output_columns),
        )
        has_positional_groups = source_groups is not None
        if source_groups is None:
            source_columns = (
                list(lateral.this.find_all(exp.Column))
                if lateral.this is not None
                else []
            )
            source_groups = [source_columns for _ in output_columns]

        for output_column, source_columns in zip(output_columns, source_groups):
            if not source_columns:
                if not has_positional_groups:
                    continue
                key = (str(output_alias), output_column, "", "")
                if key not in seen:
                    seen.add(key)
                    deps.append(LateralViewDependency(
                        output_alias=str(output_alias),
                        output_column=output_column,
                        source_column=None,
                        source_table_alias=None,
                        transform=lateral.this.sql()[:160],
                        confidence="high",
                    ))
                continue
            for source_column in source_columns:
                key = (
                    str(output_alias),
                    output_column,
                    source_column.table or "",
                    source_column.name,
                )
                if key in seen:
                    continue
                seen.add(key)
                deps.append(LateralViewDependency(
                    output_alias=str(output_alias),
                    output_column=output_column,
                    source_column=source_column.name,
                    source_table_alias=source_column.table or None,
                    transform=lateral.this.sql()[:160],
                    confidence="medium",
                ))
    return deps


def _positional_source_groups(
    expression: exp.Expression | None,
    output_count: int,
) -> list[list[exp.Column]] | None:
    if expression is None or output_count <= 0:
        return None

    if isinstance(expression, exp.Inline):
        payload = expression.this
        if isinstance(payload, exp.ArraysZip):
            groups = [
                list(argument.find_all(exp.Column))
                for argument in payload.expressions
            ]
            return groups if len(groups) == output_count else None

        if isinstance(payload, exp.Array):
            structs = [
                item
                for item in payload.expressions
                if isinstance(item, exp.Struct)
            ]
            if structs and all(
                len(struct.expressions) == output_count
                for struct in structs
            ):
                groups: list[list[exp.Column]] = [
                    [] for _ in range(output_count)
                ]
                for struct in structs:
                    for index, field in enumerate(struct.expressions):
                        value = (
                            field.expression
                            if isinstance(field, exp.PropertyEQ)
                            else field
                        )
                        groups[index].extend(value.find_all(exp.Column))
                return groups

    if (
        isinstance(expression, exp.Anonymous)
        and expression.name.lower() == "stack"
        and expression.expressions
    ):
        row_count_expression = expression.expressions[0]
        try:
            row_count = int(row_count_expression.this)
        except (AttributeError, TypeError, ValueError):
            return None
        values = expression.expressions[1:]
        if row_count <= 0:
            return None
        inferred_width = (
            (len(values) + row_count - 1) // row_count
            if values
            else 0
        )
        if inferred_width != output_count:
            return None
        groups = [[] for _ in range(output_count)]
        for index, value in enumerate(values):
            groups[index % output_count].extend(value.find_all(exp.Column))
        return groups

    return None
