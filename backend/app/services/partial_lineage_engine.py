from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain import diagnostics_model as diag_codes
from app.models import Diagnostic


@dataclass
class StructureFact:
    fact_id: str
    fact_type: str  # table_referenced / cte_declared / join_declared
    entity_id: str
    raw_text: str
    confidence: str = "low"


@dataclass
class PartialLineageIR:
    table_names: set[str] = field(default_factory=set)
    cte_names: set[str] = field(default_factory=set)
    column_edges: list[dict] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def has_content(self) -> bool:
        return bool(self.table_names or self.cte_names or self.column_edges)


class PartialLineageEngine:

    def __init__(self) -> None:
        self._table_pattern = re.compile(
            r"\b(?:from|join)\s+([a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*){0,2})\b",
            re.IGNORECASE,
        )
        self._cte_pattern = re.compile(
            r"(?:with|,)\s*([a-zA-Z_][\w]*)\s+as\s*\(",
            re.IGNORECASE,
        )

    def build_from_sql(
        self,
        sql: str,
        expression_dependencies: list | None = None,
        tree=None,
    ) -> PartialLineageIR:
        ir = PartialLineageIR()

        if tree is not None:
            self._extract_from_tree(ir, tree)
        else:
            self._extract_heuristic(ir, sql)

        if expression_dependencies:
            self._ingest_expressions(ir, expression_dependencies)

        if not ir.has_content():
            ir.diagnostics.append(
                Diagnostic(
                    code=diag_codes.LOW_CONFIDENCE_LINEAGE,
                    level="error",
                    message="No lineage evidence could be extracted from SQL.",
                )
            )

        return ir

    def _extract_from_tree(self, ir: PartialLineageIR, tree) -> None:
        from sqlglot import exp

        for table in tree.find_all(exp.Table):
            parts = [p for p in [table.catalog, table.db, table.name] if p]
            name = ".".join(parts) if parts else table.name
            ir.table_names.add(name)

        for cte in tree.find_all(exp.CTE):
            name = getattr(cte, "alias_or_name", None)
            if name:
                ir.cte_names.add(name)

    def _extract_heuristic(self, ir: PartialLineageIR, sql: str) -> None:
        for m in self._cte_pattern.finditer(sql):
            name = m.group(1)
            if not name.lower().startswith("select"):
                ir.cte_names.add(name)

        for m in self._table_pattern.finditer(sql):
            table_name = m.group(1)
            normalized = table_name.strip().lower()
            if normalized in ir.cte_names:
                continue
            if normalized.startswith("select"):
                continue
            ir.table_names.add(normalized)

    def _ingest_expressions(self, ir: PartialLineageIR, dependencies) -> None:
        for dep in dependencies:
            if not dep.column_refs:
                continue
            for ref in dep.column_refs:
                source = f"{ref.table_alias}.{ref.column_name}" if ref.table_alias else ref.column_name
                ir.column_edges.append({
                    "source": source,
                    "target": dep.output_name,
                    "transform": dep.transform_type,
                    "confidence": dep.confidence,
                })
