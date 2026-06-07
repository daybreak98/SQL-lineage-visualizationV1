"""Expression dependency extraction skeleton based on SQLGlot.

This file is intentionally written as an integration skeleton. It assumes your
project already has sqlglot installed and a ScopeResolver / NameResolver. The
minimum viable strategy is:

1. For each SELECT projection, collect all exp.Column nodes inside expression.
2. Resolve table alias to relation name and relation kind using current scope.
3. Create ColumnDependency(output=projection alias, inputs=resolved columns).

It does not try to explain every function. Function semantics can be added later
without changing the rollup service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import ColumnDependency, ColumnRef, TransformType

try:  # pragma: no cover - local tests do not require sqlglot
    from sqlglot import exp
except Exception:  # pragma: no cover
    exp = None  # type: ignore


@dataclass
class RelationInScope:
    relation_name: str
    relation_kind: str  # table | cte | subquery | unknown
    alias: str | None = None


@dataclass
class ResolveScope:
    relations_by_alias: dict[str, RelationInScope] = field(default_factory=dict)
    default_relation: RelationInScope | None = None

    def resolve_relation(self, table_or_alias: str | None) -> RelationInScope:
        if table_or_alias:
            key = table_or_alias.lower()
            if key in self.relations_by_alias:
                return self.relations_by_alias[key]
            return RelationInScope(relation_name=table_or_alias, relation_kind="unknown", alias=table_or_alias)
        if self.default_relation:
            return self.default_relation
        return RelationInScope(relation_name="", relation_kind="unknown")


class ExpressionDependencyExtractor:
    """Extract column dependencies from a SELECT projection expression."""

    def dependency_from_projection(
        self,
        projection: Any,
        output_relation: str,
        scope: ResolveScope,
    ) -> ColumnDependency:
        if exp is None:
            raise RuntimeError("sqlglot is required for ExpressionDependencyExtractor")

        output_name = self._projection_output_name(projection)
        inputs = self.extract_input_columns(projection, scope)
        return ColumnDependency(
            output=ColumnRef(output_relation, output_name, "cte" if output_relation != "final" else "output"),
            inputs=inputs,
            transform_type=self.detect_transform_type(projection),
            expression=projection.sql() if hasattr(projection, "sql") else str(projection),
            confidence="high" if inputs else "medium",
        )

    def extract_input_columns(self, expression: Any, scope: ResolveScope) -> list[ColumnRef]:
        if exp is None:
            raise RuntimeError("sqlglot is required for ExpressionDependencyExtractor")

        refs: list[ColumnRef] = []
        for col in expression.find_all(exp.Column):
            table_or_alias = col.table
            relation = scope.resolve_relation(table_or_alias)
            refs.append(
                ColumnRef(
                    relation_name=relation.relation_name,
                    column_name=col.name,
                    relation_kind=relation.relation_kind,  # type: ignore[arg-type]
                    table_alias=relation.alias,
                )
            )
        return self._dedupe(refs)

    def detect_transform_type(self, expression: Any) -> TransformType:
        if exp is None:
            raise RuntimeError("sqlglot is required for ExpressionDependencyExtractor")

        # Aggregate first, because aggregate expression can contain CASE/CAST.
        if list(expression.find_all(exp.AggFunc)):
            return "aggregate"
        if list(expression.find_all(exp.Window)):
            return "window"
        if list(expression.find_all(exp.Case)):
            return "case_when"
        if isinstance(expression, exp.Column):
            return "projection"
        if isinstance(expression, exp.Alias) and isinstance(expression.this, exp.Column):
            return "alias"
        if not list(expression.find_all(exp.Column)):
            return "constant"
        return "expression"

    def _projection_output_name(self, projection: Any) -> str:
        # SQLGlot Alias exposes .alias; raw Column exposes .name.
        alias = getattr(projection, "alias", None)
        if alias:
            return str(alias).strip("`")
        name = getattr(projection, "name", None)
        if name:
            return str(name).strip("`")
        return projection.sql() if hasattr(projection, "sql") else str(projection)

    def _dedupe(self, refs: list[ColumnRef]) -> list[ColumnRef]:
        seen = set()
        result = []
        for ref in refs:
            key = ref.lookup_key()
            if key not in seen:
                seen.add(key)
                result.append(ref)
        return result
