from __future__ import annotations

import re
from dataclasses import dataclass, field
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
    for lateral in tree.find_all(exp.Lateral):
        deps.extend(_extract_from_lateral_node(lateral))
    return deps


def extract_lateral_view_dependencies_heuristic(sql: str) -> list[LateralViewDependency]:
    """Regex-based fallback when AST is unavailable."""
    deps: list[LateralViewDependency] = []
    pattern = re.compile(
        r"\blateral\s+view\s+(?:posexplode|explode|inline)\s*\(\s*(?:split\s*\(\s*)?"
        r"(?:([a-zA-Z_]\w*)\.)?([a-zA-Z_]\w*)(?:[^)]*\))?\s*\)"
        r"\s+(\w+)\s+as\s+(\w+(?:\s*,\s*\w+)*)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(sql):
        table_alias = m.group(1) or None
        source_col = m.group(2)
        alias_table = m.group(3)
        output_cols = [c.strip() for c in m.group(4).split(",")]
        for out_col in output_cols:
            deps.append(LateralViewDependency(
                output_alias=alias_table,
                output_column=out_col,
                source_column=source_col,
                source_table_alias=table_alias,
                transform=m.group(0).strip()[:80],
                confidence="low",
            ))
    return deps


def _extract_from_lateral_node(lateral: Any) -> list[LateralViewDependency]:
    deps: list[LateralViewDependency] = []
    try:
        alias = getattr(lateral, "alias_or_name", None) or getattr(lateral, "alias", None) or "lateral"
        view_expr = getattr(lateral, "this", None)
        if view_expr is None:
            return deps
        sql = str(view_expr)
        columns = []
        for col in view_expr.find_all(exp.Column):
            if col.table:
                deps.append(LateralViewDependency(
                    output_alias=str(alias),
                    output_column=col.name,
                    source_column=col.name,
                    source_table_alias=col.table,
                    transform=sql[:80],
                    confidence="medium",
                ))
    except Exception:
        pass
    return deps
