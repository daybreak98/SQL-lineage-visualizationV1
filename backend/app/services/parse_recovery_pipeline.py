from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.models import Diagnostic


@dataclass
class ParseRecoveryResult:
    sql: str
    tree: Any = None
    full_ast_available: bool = False
    structure_facts: list[dict] = field(default_factory=list)
    expression_dependencies: list = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def can_build_graph(self) -> bool:
        return self.full_ast_available or bool(self.structure_facts)


class ParseRecoveryPipeline:
    """Bridge that wraps existing complex_sql_guard and adds recovery extraction.

    When the complex_sql_guard produces a tree, we use it directly.
    When it fails, we extract structure facts heuristically from the SQL.
    """

    TABLE_PATTERN = re.compile(
        r"\b(?:from|join)\s+([a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*){0,2})\b",
        re.IGNORECASE,
    )
    CTE_PATTERN = re.compile(
        r"(?:with|,)\s*([a-zA-Z_][\w]*)\s+as\s*\(",
        re.IGNORECASE,
    )

    def recover_from_parse_result(self, parse_result) -> ParseRecoveryResult:
        tree = parse_result.tree
        full_ast = tree is not None
        facts: list[dict] = []
        expr_deps = []

        if full_ast:
            facts_tree = self._extract_table_facts_from_tree(tree)
            facts.extend(facts_tree)
            expr_deps = self._extract_expression_deps_from_tree(tree)

        if not facts:
            facts_heuristic = self._extract_table_facts_heuristic(
                getattr(parse_result, "analysis_sql", "")
                or getattr(parse_result, "normalized_sql", "")
                or ""
            )
            facts.extend(facts_heuristic)

        diags = []
        if not full_ast:
            from app.domain import diagnostics_model as diag_codes
            diags.append(
                Diagnostic(
                    code=diag_codes.PARTIAL_PARSE_RESULT,
                    level="warning",
                    message="Lineage is built from heuristic structure extraction because full SQL parse failed.",
                )
            )

        return ParseRecoveryResult(
            sql=getattr(parse_result, "normalized_sql", "") or "",
            tree=tree,
            full_ast_available=full_ast,
            structure_facts=facts,
            expression_dependencies=expr_deps,
            diagnostics=diags,
        )

    def _extract_table_facts_from_tree(self, tree) -> list[dict]:
        from sqlglot import exp

        facts: list[dict] = []
        seen = set()

        for table in tree.find_all(exp.Table):
            parts = [p for p in [table.catalog, table.db, table.name] if p]
            name = ".".join(parts) if parts else table.name
            if name not in seen:
                seen.add(name)
                facts.append({"fact_type": "table_referenced", "entity_id": f"table:{name}", "label": name})

        for cte in tree.find_all(exp.CTE):
            name = getattr(cte, "alias_or_name", None)
            if name and name not in seen:
                seen.add(name)
                facts.append({"fact_type": "cte_declared", "entity_id": f"cte:{name}", "label": name})

        return facts

    def _extract_table_facts_heuristic(self, sql: str) -> list[dict]:
        facts: list[dict] = []
        seen = set()

        for m in self.CTE_PATTERN.finditer(sql):
            name = m.group(1)
            key = name.lower()
            if key in seen or key.startswith("select"):
                continue
            seen.add(key)
            facts.append({"fact_type": "cte_declared", "entity_id": f"cte:{name}", "label": name, "confidence": "low"})

        for m in self.TABLE_PATTERN.finditer(sql):
            name = m.group(1).strip().lower()
            if name in seen or name == "select":
                continue
            seen.add(name)
            facts.append({"fact_type": "table_referenced", "entity_id": f"table:{name}", "label": name, "confidence": "low"})

        return facts

    def _extract_expression_deps_from_tree(self, tree) -> list:
        try:
            from sqlglot import exp
            deps = []
            for item in getattr(tree, "expressions", []):
                name = getattr(item, "alias_or_name", None) or self._safe_sql(item)[:64]
                sql = self._safe_sql(item)
                refs = []
                for col in item.find_all(exp.Column):
                    refs.append({
                        "table_alias": getattr(col, "table", None),
                        "column_name": getattr(col, "name", None) or self._safe_sql(col),
                    })
                if refs:
                    deps.append({
                        "output_name": name,
                        "expression_sql": sql,
                        "column_refs": refs,
                        "transform_type": self._classify_transform(item),
                    })
            return deps
        except Exception:
            return []

    @staticmethod
    def _safe_sql(node) -> str:
        try:
            if hasattr(node, "sql"):
                return node.sql()
        except Exception:
            pass
        return str(node)

    @staticmethod
    def _classify_transform(expression) -> str:
        sql = str(expression).lower()
        if "over (" in sql or any(k in sql for k in ("row_number", "rank(", "dense_rank", "lead(", "lag(")):
            return "window"
        if "case" in sql and "when" in sql:
            return "case_when"
        if any(k in sql for k in ("count(", "sum(", "avg(", "min(", "max(")):
            return "aggregate"
        return "expression"
