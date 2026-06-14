"""
Reference implementation: query_structure_service.py

Goal:
- Analyze SQL structure once after parse_sql().
- Replace controller-level CTE / non-CTE big branching with a unified structure object.

This code assumes sqlglot Expression objects.
Adjust imports and diagnostic model to match the real project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Set

try:
    from sqlglot import exp
except Exception:  # pragma: no cover - reference fallback for static reading
    exp = None  # type: ignore


@dataclass
class QueryStructureResult:
    has_cte: bool = False
    has_subquery: bool = False
    cte_names: Set[str] = field(default_factory=set)
    physical_table_names: Set[str] = field(default_factory=set)
    final_select_source_names: Set[str] = field(default_factory=set)
    diagnostics: list[Any] = field(default_factory=list)


def analyze_query_structure(tree: Any) -> QueryStructureResult:
    """Extract high-level query structure from a sqlglot AST."""
    cte_names = extract_cte_names(tree)
    physical_table_names = extract_physical_table_names(tree, cte_names=cte_names)
    final_select_source_names = extract_final_select_source_names(tree)
    has_subquery = _has_subquery(tree)

    return QueryStructureResult(
        has_cte=bool(cte_names),
        has_subquery=has_subquery,
        cte_names=cte_names,
        physical_table_names=physical_table_names,
        final_select_source_names=final_select_source_names,
        diagnostics=[],
    )


def extract_cte_names(tree: Any) -> Set[str]:
    """Return WITH CTE definition names.

    Example:
        WITH order_base AS (...) SELECT ...
        -> {"order_base"}
    """
    names: Set[str] = set()
    if exp is None or tree is None:
        return names

    for cte in tree.find_all(exp.CTE):
        name = getattr(cte, "alias_or_name", None)
        if name:
            names.add(_clean_identifier(name))
    return names


def extract_physical_table_names(tree: Any, cte_names: Set[str] | None = None) -> Set[str]:
    """Return physical table names from all FROM/JOIN references, excluding CTE names."""
    cte_norm = {_norm_identifier(x) for x in (cte_names or set())}
    names: Set[str] = set()
    if exp is None or tree is None:
        return names

    for table in tree.find_all(exp.Table):
        full_name = _table_full_name(table)
        if not full_name:
            continue
        if _norm_identifier(_last_part(full_name)) in cte_norm:
            continue
        names.add(full_name)
    return names


def extract_final_select_source_names(tree: Any) -> Set[str]:
    """Return source names from the outermost SELECT's FROM/JOIN only.

    This is used by CTE final-hop lineage.
    It should not walk into CTE bodies.
    """
    names: Set[str] = set()
    if exp is None or tree is None:
        return names

    select = _outer_select(tree)
    if select is None:
        return names

    # sqlglot stores FROM under "from_" in recent versions.
    from_expr = select.args.get("from") or select.args.get("from_")
    if from_expr is not None:
        names.update(_direct_table_names(from_expr))

    for join in select.args.get("joins") or []:
        names.update(_direct_table_names(join))

    return names


def _outer_select(tree: Any) -> Optional[Any]:
    """Best-effort extraction of outermost Select.

    In many cases parse_one() returns exp.Select directly.
    For wrapper expressions, try `.this`.
    """
    if exp is None or tree is None:
        return None
    if isinstance(tree, exp.Select):
        return tree
    this = getattr(tree, "this", None)
    if isinstance(this, exp.Select):
        return this
    # Fallback: first Select in DFS is usually the outer select in sqlglot.
    return tree.find(exp.Select)


def _direct_table_names(expr_node: Any) -> Set[str]:
    """Return table names directly under FROM/JOIN.

    This is intentionally conservative; subquery internals should not leak here.
    """
    result: Set[str] = set()
    if exp is None or expr_node is None:
        return result

    # JOIN.this is commonly a Table/Subquery.
    candidate = getattr(expr_node, "this", None)
    if isinstance(candidate, exp.Table):
        name = _table_full_name(candidate)
        if name:
            result.add(name)
        return result

    # FROM expressions can contain one or more direct expressions.
    expressions: Iterable[Any] = getattr(expr_node, "expressions", None) or []
    for item in expressions:
        if isinstance(item, exp.Table):
            name = _table_full_name(item)
            if name:
                result.add(name)
    return result


def _has_subquery(tree: Any) -> bool:
    if exp is None or tree is None:
        return False
    return any(True for _ in tree.find_all(exp.Subquery))


def _table_full_name(table: Any) -> str:
    # sqlglot Table.sql() may include quotes; prefer catalog/db/name parts when available.
    catalog = _safe_text(getattr(table, "catalog", None))
    db = _safe_text(getattr(table, "db", None))
    name = _safe_text(getattr(table, "name", None) or getattr(table, "this", None))
    parts = [p for p in [catalog, db, name] if p]
    return ".".join(_clean_identifier(p) for p in parts)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # sqlglot Identifier often has .this
    inner = getattr(value, "this", None)
    if isinstance(inner, str):
        return inner
    return str(value)


def _clean_identifier(name: str) -> str:
    return name.strip().strip("`\"")


def _norm_identifier(name: str) -> str:
    return _clean_identifier(name).lower()


def _last_part(name: str) -> str:
    return _clean_identifier(name).split(".")[-1]
