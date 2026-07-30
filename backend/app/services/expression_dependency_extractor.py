"""Expression dependency extraction based on SQLGlot AST.

For each SELECT projection, collects all Column nodes, resolves table aliases
to relation names and kinds (table/cte/unknown), produces ColumnDependency.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from sqlglot import exp

from app.domain.cte_rollup_models import ColumnDependency, ColumnRef, TransformType


@dataclass
class RelationInScope:
    relation_name: str
    relation_kind: str  # table | cte | subquery | unknown
    alias: Optional[str] = None


@dataclass
class ResolveScope:
    relations_by_alias: Dict[str, RelationInScope] = field(default_factory=dict)
    default_relation: Optional[RelationInScope] = None

    def resolve_relation(self, table_or_alias: Optional[str]) -> RelationInScope:
        if table_or_alias:
            key = table_or_alias.lower().strip("`")
            if key in self.relations_by_alias:
                return self.relations_by_alias[key]
            return RelationInScope(
                relation_name=table_or_alias,
                relation_kind="unknown",
                alias=table_or_alias,
            )
        if self.default_relation:
            return self.default_relation
        return RelationInScope(relation_name="", relation_kind="unknown")


def build_scope_from_cte_body(
    select_node: exp.Select,
    cte_names: Set[str],
) -> ResolveScope:
    scope = ResolveScope()
    # FROM table or subquery
    from_expr = select_node.args.get("from_") or select_node.args.get("from")
    if from_expr is not None:
        _add_source_to_scope(from_expr, scope, cte_names)

    # JOIN tables or subqueries
    for join in select_node.args.get("joins") or []:
        _add_source_to_scope(join, scope, cte_names)

    return scope


def _add_source_to_scope(
    source: Any, scope: ResolveScope, cte_names: Set[str],
) -> None:
    this = getattr(source, "this", None)
    alias = getattr(source, "alias", None) or getattr(this, "alias", None) or ""

    if isinstance(this, exp.Table):
        name = _table_name(this)
        key = alias.lower() if alias else name.lower().strip("`")
        kind = "cte" if name.lower().strip("`") in cte_names else "table"
        rel = RelationInScope(relation_name=name, relation_kind=kind, alias=alias or name)
    elif isinstance(this, exp.Subquery):
        sub_alias = getattr(this, "alias", None) or alias
        rel = RelationInScope(
            relation_name=sub_alias or "__subquery__",
            relation_kind="subquery",
            alias=sub_alias or "",
        )
        key = sub_alias.lower() if sub_alias else ""
    else:
        return

    if key:
        scope.relations_by_alias[key] = rel
    if scope.default_relation is None:
        scope.default_relation = rel


def _table_name(table: exp.Table) -> str:
    parts = [p for p in [table.catalog, table.db, table.name] if p]
    return ".".join(parts) if parts else (table.name or "")


class ExpressionDependencyExtractor:
    """Extract column dependencies from SELECT projection expressions."""

    def dependency_from_projection(
        self,
        projection: Any,
        output_relation: str,
        scope: ResolveScope,
    ) -> Optional[ColumnDependency]:
        output_name = getattr(projection, "alias_or_name", None)
        if not output_name:
            output_name = self._projection_output_name(projection)
        if not output_name:
            return None

        inputs = self.extract_input_columns(projection, scope)
        return ColumnDependency(
            output=ColumnRef(
                output_relation, output_name,
                "cte" if output_relation != "final" else "output",
            ),
            inputs=inputs,
            transform_type=self.detect_transform_type(projection),
            expression=projection.sql() if hasattr(projection, "sql")
            else str(projection),
            confidence="high" if inputs else "medium",
        )

    def extract_input_columns(
        self, expression: Any, scope: ResolveScope,
    ) -> List[ColumnRef]:
        refs: List[ColumnRef] = []
        for relation in _rowset_aggregate_relations(expression, scope):
            refs.append(
                ColumnRef(
                    relation_name=relation.relation_name,
                    column_name="*",
                    relation_kind=relation.relation_kind,
                    table_alias=relation.alias,
                )
            )
        for col in source_columns_with_named_windows(expression):
            if isinstance(col.this, exp.Star):
                continue  # skip star references inside qualified stars
            table_or_alias = col.table
            relation = scope.resolve_relation(table_or_alias)
            refs.append(
                ColumnRef(
                    relation_name=relation.relation_name,
                    column_name=col.name,
                    relation_kind=relation.relation_kind,
                    table_alias=relation.alias,
                )
            )
        return self._dedupe(refs)

    def detect_transform_type(self, expression: Any) -> TransformType:
        agg_funcs = list(expression.find_all(exp.AggFunc))
        if agg_funcs:
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
        alias = getattr(projection, "alias", None)
        if alias:
            return str(alias).strip("`")
        name = getattr(projection, "name", None)
        if name:
            return str(name).strip("`")
        return ""

    def _dedupe(self, refs: List[ColumnRef]) -> List[ColumnRef]:
        seen: Set = set()
        result: List[ColumnRef] = []
        for ref in refs:
            key = ref.lookup_key()
            if key not in seen:
                seen.add(key)
                result.append(ref)
        return result


def _rowset_aggregate_relations(
    expression: Any,
    scope: ResolveScope,
) -> List[RelationInScope]:
    projection_select = expression.find_ancestor(exp.Select)
    result: List[RelationInScope] = []
    seen: Set[tuple[str, str, str]] = set()

    for aggregate in expression.find_all(exp.AggFunc):
        if aggregate.find_ancestor(exp.Select) is not projection_select:
            continue
        columns = list(aggregate.find_all(exp.Column))
        if any(not isinstance(column.this, exp.Star) for column in columns):
            continue

        qualifiers = {
            column.table.lower().strip("`")
            for column in columns
            if isinstance(column.this, exp.Star) and column.table
        }
        if qualifiers:
            relations = [scope.resolve_relation(name) for name in qualifiers]
        else:
            relations = list(scope.relations_by_alias.values())
            if not relations and scope.default_relation is not None:
                relations = [scope.default_relation]

        for relation in relations:
            if relation.relation_kind == "unknown" or not relation.relation_name:
                continue
            key = (
                relation.relation_kind,
                relation.relation_name.lower().strip("`"),
                (relation.alias or "").lower().strip("`"),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(relation)

    return result


def source_columns_with_named_windows(expression: Any) -> List[exp.Column]:
    """Collect expression columns plus referenced WINDOW-clause definitions."""
    columns = list(expression.find_all(exp.Column))
    select = expression.find_ancestor(exp.Select)
    if select is None:
        return columns

    definitions = {
        window.name.lower().strip("`"): window
        for window in (select.args.get("windows") or [])
        if window.name
    }
    pending = [
        str(window.alias).lower().strip("`")
        for window in expression.find_all(exp.Window)
        if window.alias
    ]
    visited: Set[str] = set()
    while pending:
        name = pending.pop()
        if not name or name in visited:
            continue
        visited.add(name)
        definition = definitions.get(name)
        if definition is None:
            continue
        columns.extend(definition.find_all(exp.Column))
        if definition.alias:
            pending.append(str(definition.alias).lower().strip("`"))
    return columns
