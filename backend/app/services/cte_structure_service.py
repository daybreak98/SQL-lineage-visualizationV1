from __future__ import annotations

import time
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError as SqlglotParseError

from app.domain import diagnostics_model as diag_codes
from app.models import Diagnostic


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

    with_expr = _get_arg(tree, "with")
    if with_expr is None:
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

    cte_names = {cte.alias_or_name for cte in with_expr.expressions}
    nodes_by_id: dict[str, StructureNode] = {}
    edges_by_id: dict[str, StructureEdge] = {}

    for cte in with_expr.expressions:
        cte_name = cte.alias_or_name
        cte_id = _cte_id(cte_name)
        nodes_by_id[cte_id] = StructureNode(id=cte_id, node_type="cte", label=cte_name)

    for cte in with_expr.expressions:
        cte_name = cte.alias_or_name
        target_id = _cte_id(cte_name)
        for table in cte.this.find_all(exp.Table):
            source_name = _table_name_without_alias(table, dialect)
            if source_name == cte_name:
                continue
            if source_name in cte_names:
                source_id = _cte_id(source_name)
                edge_type = "cte_dependency"
            else:
                source_id = _physical_table_id(source_name)
                edge_type = "table_to_cte"
                nodes_by_id[source_id] = StructureNode(
                    id=source_id,
                    node_type="table",
                    label=source_name,
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

    return _result(
        started=started,
        status="success",
        confidence_level="medium",
        nodes=list(nodes_by_id.values()),
        edges=list(edges_by_id.values()),
        stage_status="success",
    )


def _final_query_sources(tree: exp.Expression, dialect: str) -> list[exp.Table]:
    from_expr = _get_arg(tree, "from")
    sources: list[exp.Table] = []
    if from_expr is not None and isinstance(from_expr.this, exp.Table):
        sources.append(from_expr.this)
    for join in tree.args.get("joins") or []:
        if isinstance(join.this, exp.Table):
            sources.append(join.this)
    return sources


def _get_arg(tree: exp.Expression, key: str):
    return tree.args.get(key) or tree.args.get(f"{key}_")


def _table_name_without_alias(table: exp.Table, dialect: str) -> str:
    parts = [part for part in [table.catalog, table.db, table.name] if part]
    if parts:
        return ".".join(parts)
    return table.sql(dialect=dialect).split(" AS ")[0]


def _cte_id(name: str) -> str:
    return f"cte:{name}"


def _physical_table_id(name: str) -> str:
    return f"physical_table:{name}"


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
