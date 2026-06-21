from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlglot import exp


@dataclass
class LateralViewDependency:
    output_alias: str
    output_column: str
    source_column: str
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
        source_columns = list(lateral.this.find_all(exp.Column)) if lateral.this is not None else []

        for output_column in output_columns:
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
