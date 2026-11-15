"""
Scope extraction helpers for CTE SELECT bodies.

The key point: ExpressionAnalyzer depends_on values must be resolved through the
current SELECT scope before they are written into CTE schemas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

try:
    from sqlglot import exp
except Exception:  # pragma: no cover - reference code can be imported without sqlglot
    exp = None

from cte_schema_models import RelationRef


@dataclass
class SelectScope:
    alias_to_relation: dict[str, RelationRef] = field(default_factory=dict)
    visible_relations: list[RelationRef] = field(default_factory=list)

    def add_relation(self, relation: RelationRef) -> None:
        # Register real relation name.
        self.alias_to_relation[relation.relation_name.lower()] = relation

        # Register alias if exists.
        if relation.alias:
            self.alias_to_relation[relation.alias.lower()] = relation

        # Keep visible relation order for single-source inference.
        if relation.relation_name.lower() not in {r.relation_name.lower() for r in self.visible_relations}:
            self.visible_relations.append(relation)

    def resolve_qualifier(self, qualifier: str) -> RelationRef | None:
        return self.alias_to_relation.get(qualifier.lower())


def _relation_kind(name: str, cte_names: set[str]) -> str:
    return "cte" if name.lower() in {c.lower() for c in cte_names} else "table"


def _table_name(table_expr) -> str | None:
    """Extract table name from a sqlglot exp.Table."""
    if table_expr is None:
        return None
    try:
        return table_expr.name or str(table_expr.this)
    except Exception:
        return None


def _table_alias(table_expr) -> str | None:
    try:
        return table_expr.alias_or_name if table_expr.alias else None
    except Exception:
        return None


def extract_select_scope(select_expr, cte_names: set[str]) -> SelectScope:
    """
    Extract alias -> relation mapping from the current SELECT's FROM/JOIN clauses.

    Example:
        from search_base a join dim_city c

    Returns mappings:
        a -> search_base
        search_base -> search_base
        c -> dim_city
        dim_city -> dim_city

    Notes:
        - This function intentionally does not walk into nested SELECTs.
        - If the project already has a table reference extractor, prefer reusing it.
    """
    scope = SelectScope()

    if exp is None or select_expr is None:
        return scope

    # Best-effort: use sqlglot Table nodes visible under this select.
    # For production, avoid descending into nested subqueries if that causes false positives.
    for table in select_expr.find_all(exp.Table):
        name = _table_name(table)
        if not name:
            continue
        alias = _table_alias(table)
        scope.add_relation(
            RelationRef(
                relation_name=name,
                relation_kind=_relation_kind(name, cte_names),
                alias=alias,
            )
        )

    return scope
