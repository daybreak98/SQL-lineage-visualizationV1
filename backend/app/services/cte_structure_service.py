from __future__ import annotations

import time
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError as SqlglotParseError

from app.domain import diagnostics_model as diag_codes
from app.models import Diagnostic
from app.services.sqlglot_compat import (
    get_from_expression,
    get_with_expression,
    is_set_operation,
)


@dataclass(frozen=True)
class StructureNode:
    id: str
    node_type: str
    label: str


@dataclass(frozen=True)
class StructureEdge:
    source: str
    target: str
    edge_type: str

    @property
    def id(self) -> str:
        return f"edge:{self.source}->{self.target}"


@dataclass
class CteStructureResult:
    status: str
    confidence_level: str
    nodes: list[StructureNode] = field(default_factory=list)
    edges: list[StructureEdge] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    unsupported_features: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    stage_statuses: list[dict[str, object]] = field(default_factory=list)

    @property
    def has_cte(self) -> bool:
        return any(node.node_type == "cte" for node in self.nodes)


def analyze_cte_structure(sql: str, dialect: str = "spark",
                           tree: exp.Expression | None = None) -> CteStructureResult:
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

    with_expr = get_with_expression(tree)
    named_subqueries = _named_subqueries(tree)
    if with_expr is None and not named_subqueries:
        return _result(
            started=started,
            status="partial",
            confidence_level="unknown",
            diagnostics=[
                Diagnostic(
                    code=diag_codes.UNSUPPORTED_COMPLEX_QUERY,
                    level="warning",
                    message="C05 structure analysis requires a WITH/CTE query.",
                )
            ],
            unsupported_features=["non_cte_query"],
            stage_status="partial",
        )

    cte_expressions = list(with_expr.expressions) if with_expr is not None else []
    cte_names = {cte.alias_or_name for cte in cte_expressions}
    nodes_by_id: dict[str, StructureNode] = {}
    edges_by_id: dict[str, StructureEdge] = {}

    for cte in cte_expressions:
        cte_name = cte.alias_or_name
        cte_id = _cte_id(cte_name)
        nodes_by_id[cte_id] = StructureNode(id=cte_id, node_type="cte", label=cte_name)

    for alias in named_subqueries:
        subquery_id = _subquery_id(alias)
        nodes_by_id[subquery_id] = StructureNode(
            id=subquery_id,
            node_type="subquery",
            label=alias,
        )

    for cte in cte_expressions:
        cte_name = cte.alias_or_name
        target_id = _cte_id(cte_name)
        for source in _direct_sources(cte.this):
            source_id, source_type, source_label = _source_identity(
                source, dialect, cte_names
            )
            if not source_id or source_id == target_id:
                continue
            nodes_by_id.setdefault(
                source_id,
                StructureNode(id=source_id, node_type=source_type, label=source_label),
            )
            edge_type = {
                "cte": "cte_dependency",
                "subquery": "subquery_dependency",
            }.get(source_type, "table_to_cte")
            edge = StructureEdge(source=source_id, target=target_id, edge_type=edge_type)
            edges_by_id[edge.id] = edge

    for alias, subquery in named_subqueries.items():
        target_id = _subquery_id(alias)
        for source in _direct_sources(_subquery_body(subquery)):
            source_id, source_type, source_label = _source_identity(
                source, dialect, cte_names
            )
            if not source_id or source_id == target_id:
                continue
            nodes_by_id.setdefault(
                source_id,
                StructureNode(id=source_id, node_type=source_type, label=source_label),
            )
            edge_type = (
                "table_to_subquery"
                if source_type == "table"
                else "subquery_dependency"
            )
            edge = StructureEdge(source=source_id, target=target_id, edge_type=edge_type)
            edges_by_id[edge.id] = edge

    result_id = "query_result:final"
    nodes_by_id[result_id] = StructureNode(
        id=result_id,
        node_type="output",
        label="Query Result",
    )
    for table in _final_query_sources(tree, dialect):
        source_name = _table_name_without_alias(table, dialect)
        source_id = _cte_id(source_name) if source_name in cte_names else _physical_table_id(source_name)
        if source_id not in nodes_by_id:
            nodes_by_id[source_id] = StructureNode(
                id=source_id,
                node_type="table",
                label=source_name,
            )
        edge_type = "cte_to_result" if source_name in cte_names else "table_to_result"
        edge = StructureEdge(source=source_id, target=result_id, edge_type=edge_type)
        edges_by_id[edge.id] = edge

    aliases_by_subquery_identity = {
        id(expression): alias for alias, expression in named_subqueries.items()
    }
    for alias, subquery in named_subqueries.items():
        target_id, edge_type = _containing_relation_target(
            subquery,
            aliases_by_subquery_identity,
            result_id,
        )
        source_id = _subquery_id(alias)
        if not target_id or source_id == target_id:
            continue
        edge = StructureEdge(
            source=source_id,
            target=target_id,
            edge_type=edge_type,
        )
        edges_by_id[edge.id] = edge

    return _result(
        started=started,
        status="success",
        confidence_level="medium",
        nodes=list(nodes_by_id.values()),
        edges=list(edges_by_id.values()),
        stage_status="success",
    )


def _final_query_sources(tree: exp.Expression, dialect: str) -> list[exp.Table]:
    outer_select = _outer_select(tree)
    if outer_select is None:
        return []
    from_expr = get_from_expression(outer_select)
    sources: list[exp.Table] = []
    if from_expr is not None and isinstance(from_expr.this, exp.Table):
        sources.append(from_expr.this)
    for join in outer_select.args.get("joins") or []:
        if isinstance(join.this, exp.Table):
            sources.append(join.this)
    return sources


def _named_subqueries(tree: exp.Expression) -> dict[str, exp.Expression]:
    result: dict[str, exp.Expression] = {}
    for subquery_index, subquery in enumerate(tree.find_all(exp.Subquery), start=1):
        alias = subquery.alias_or_name
        if not alias:
            alias_expression = subquery.find_ancestor(exp.Alias)
            alias = alias_expression.alias_or_name if alias_expression is not None else ""
        if not alias:
            predicate = subquery.parent
            prefix = "in_subquery" if isinstance(predicate, exp.In) else "subquery"
            alias = f"{prefix}_{subquery_index}"
        if alias:
            result[alias] = subquery

    exists_index = 0
    for exists in tree.find_all(exp.Exists):
        query = exists.this
        if not isinstance(query, exp.Query) or isinstance(query, exp.Subquery):
            continue
        exists_index += 1
        result[f"exists_subquery_{exists_index}"] = query
    return result


def _subquery_body(subquery: exp.Expression) -> exp.Expression:
    if isinstance(subquery, exp.Subquery):
        return subquery.this
    return subquery


def _outer_select(tree: exp.Expression | None) -> exp.Select | None:
    if isinstance(tree, exp.Select):
        return tree
    if isinstance(tree, exp.Subquery):
        return _outer_select(tree.this)
    expression = getattr(tree, "expression", None)
    if isinstance(expression, exp.Select):
        return expression
    this = getattr(tree, "this", None)
    if isinstance(this, exp.Select):
        return this
    return None


def _direct_sources(tree: exp.Expression | None) -> list[exp.Expression]:
    if is_set_operation(tree):
        return _direct_sources(tree.this) + _direct_sources(tree.expression)
    select = _outer_select(tree)
    if select is None:
        return []
    result: list[exp.Expression] = []
    from_expr = get_from_expression(select)
    if from_expr is not None and isinstance(from_expr.this, (exp.Table, exp.Subquery)):
        result.append(from_expr.this)
    for join in select.args.get("joins") or []:
        if isinstance(join.this, (exp.Table, exp.Subquery)):
            result.append(join.this)
    return result


def _containing_relation_target(
    subquery: exp.Expression,
    aliases_by_subquery_identity: dict[int, str],
    result_id: str,
) -> tuple[str, str]:
    parent = subquery.parent
    while parent is not None:
        parent_alias = aliases_by_subquery_identity.get(id(parent))
        if parent_alias:
            return _subquery_id(parent_alias), "subquery_dependency"
        if isinstance(parent, exp.CTE):
            return _cte_id(parent.alias_or_name), "subquery_dependency"
        parent = parent.parent
    return result_id, "subquery_to_result"


def _source_identity(
    source: exp.Expression,
    dialect: str,
    cte_names: set[str],
) -> tuple[str, str, str]:
    if isinstance(source, exp.Subquery):
        alias = source.alias_or_name
        return (_subquery_id(alias), "subquery", alias) if alias else ("", "", "")
    if isinstance(source, exp.Table):
        name = _table_name_without_alias(source, dialect)
        if name in cte_names:
            return _cte_id(name), "cte", name
        return _physical_table_id(name), "table", name
    return "", "", ""


def _table_name_without_alias(table: exp.Table, dialect: str) -> str:
    parts = [part for part in [table.catalog, table.db, table.name] if part]
    if parts:
        return ".".join(parts)
    return table.sql(dialect=dialect).split(" AS ")[0]


def _cte_id(name: str) -> str:
    return f"cte:{name}"


def _physical_table_id(name: str) -> str:
    return f"physical_table:{name}"


def _subquery_id(name: str) -> str:
    return f"subquery:{name}"


def _result(
    started: float,
    status: str,
    confidence_level: str,
    nodes: list[StructureNode] | None = None,
    edges: list[StructureEdge] | None = None,
    diagnostics: list[Diagnostic] | None = None,
    unsupported_features: list[str] | None = None,
    stage_status: str = "success",
) -> CteStructureResult:
    elapsed = int((time.time() - started) * 1000)
    diagnostic_codes = [diagnostic.code for diagnostic in diagnostics or []]
    return CteStructureResult(
        status=status,
        confidence_level=confidence_level,
        nodes=nodes or [],
        edges=edges or [],
        diagnostics=diagnostics or [],
        unsupported_features=unsupported_features or [],
        elapsed_ms=elapsed,
        stage_statuses=[
            {
                "stage": "cte_subquery_rollup",
                "status": stage_status,
                "elapsed_ms": elapsed,
                "diagnostic_codes": diagnostic_codes,
                "message": "CTE structure dependencies resolved.",
            }
        ],
    )
