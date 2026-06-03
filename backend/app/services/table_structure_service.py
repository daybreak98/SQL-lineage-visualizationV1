from __future__ import annotations

import time
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError as SqlglotParseError

from app.domain import diagnostics_model as diag_codes
from app.models import Diagnostic
from app.services.cte_structure_service import StructureEdge, StructureNode


@dataclass
class TableStructureResult:
    status: str
    confidence_level: str
    nodes: list[StructureNode] = field(default_factory=list)
    edges: list[StructureEdge] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    unsupported_features: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    stage_statuses: list[dict[str, object]] = field(default_factory=list)


def analyze_table_structure(sql: str, dialect: str = "spark",
                             tree: exp.Expression | None = None) -> TableStructureResult:
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

    if tree.args.get("with_") is not None:
        return _result(
            started=started,
            status="partial",
            confidence_level="unknown",
            diagnostics=[
                Diagnostic(
                    code=diag_codes.UNSUPPORTED_COMPLEX_QUERY,
                    level="warning",
                    message="Table structure analysis for WITH queries is handled by CTE structure analysis.",
                )
            ],
            unsupported_features=["cte_query"],
            stage_status="partial",
        )

    tables = _query_sources(tree, dialect)
    if not tables:
        return _result(
            started=started,
            status="partial",
            confidence_level="unknown",
            diagnostics=[
                Diagnostic(
                    code=diag_codes.UNSUPPORTED_COMPLEX_QUERY,
                    level="warning",
                    message="No physical source table can be resolved for table structure graph.",
                )
            ],
            unsupported_features=["missing_source_table"],
            stage_status="partial",
        )

    nodes_by_id: dict[str, StructureNode] = {
        "query_result:final": StructureNode(
            id="query_result:final",
            node_type="output",
            label="Query Result",
        )
    }
    edges_by_id: dict[str, StructureEdge] = {}

    for table_name in tables:
        source_id = f"physical_table:{table_name}"
        nodes_by_id[source_id] = StructureNode(
            id=source_id,
            node_type="table",
            label=table_name,
        )
        edge = StructureEdge(
            source=source_id,
            target="query_result:final",
            edge_type="table_to_result",
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


def _query_sources(tree: exp.Expression, dialect: str) -> list[str]:
    sources: list[str] = []
    from_expr = tree.args.get("from_")
    if from_expr is not None and isinstance(from_expr.this, exp.Table):
        sources.append(_table_name_without_alias(from_expr.this, dialect))
    for join in tree.args.get("joins") or []:
        if isinstance(join.this, exp.Table):
            sources.append(_table_name_without_alias(join.this, dialect))
    return list(dict.fromkeys(sources))


def _table_name_without_alias(table: exp.Table, dialect: str) -> str:
    parts = [part for part in [table.catalog, table.db, table.name] if part]
    if parts:
        return ".".join(parts)
    return table.sql(dialect=dialect).split(" AS ")[0]


def _result(
    started: float,
    status: str,
    confidence_level: str,
    nodes: list[StructureNode] | None = None,
    edges: list[StructureEdge] | None = None,
    diagnostics: list[Diagnostic] | None = None,
    unsupported_features: list[str] | None = None,
    stage_status: str = "success",
) -> TableStructureResult:
    elapsed = int((time.time() - started) * 1000)
    diagnostic_codes = [diagnostic.code for diagnostic in diagnostics or []]
    return TableStructureResult(
        status=status,
        confidence_level=confidence_level,
        nodes=nodes or [],
        edges=edges or [],
        diagnostics=diagnostics or [],
        unsupported_features=unsupported_features or [],
        elapsed_ms=elapsed,
        stage_statuses=[
            {
                "stage": "table_structure",
                "status": stage_status,
                "elapsed_ms": elapsed,
                "diagnostic_codes": diagnostic_codes,
                "message": "Physical table to Query Result structure resolved.",
            }
        ],
    )
