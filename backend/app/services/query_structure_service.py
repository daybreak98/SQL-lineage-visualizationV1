"""Unified query structure analysis — replaces controller-level CTE/non-CTE branching.

Extracts: CTE names, physical table names, final SELECT source names, subquery detection.
Makes all of this available through a single QueryStructureResult.
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional, Set

from sqlglot import exp


@dataclass
class QueryStructureResult:
    has_cte: bool = False
    has_subquery: bool = False
    cte_names: Set[str] = field(default_factory=set)
    physical_table_names: Set[str] = field(default_factory=set)
    final_select_source_names: Set[str] = field(default_factory=set)
    diagnostics: List[Any] = field(default_factory=list)


def analyze_query_structure(tree: Any) -> QueryStructureResult:
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
    )


def extract_cte_names(tree: Any) -> Set[str]:
    names: Set[str] = set()
    if tree is None:
        return names
    for cte in tree.find_all(exp.CTE):
        name = getattr(cte, "alias_or_name", None)
        if name:
            names.add(_clean_identifier(name))
    return names


def extract_physical_table_names(tree: Any, cte_names: Optional[Set[str]] = None) -> Set[str]:
    cte_norm = {_norm_identifier(x) for x in (cte_names or set())}
    names: Set[str] = set()
    if tree is None:
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
    names: Set[str] = set()
    if tree is None:
        return names
    sel = _outer_select(tree)
    if sel is None:
        return names
    from_expr = sel.args.get("from_") or sel.args.get("from")
    if from_expr is not None:
        names.update(_direct_table_names(from_expr))
    for join in sel.args.get("joins") or []:
        names.update(_direct_table_names(join))
    return names


def _outer_select(tree: Any) -> Optional[Any]:
    if isinstance(tree, exp.Select):
        return tree
    this = getattr(tree, "this", None)
    if isinstance(this, exp.Select):
        return this
    found = tree.find(exp.Select)
    return found if isinstance(found, exp.Select) else None


def _direct_table_names(expr_node: Any) -> Set[str]:
    result: Set[str] = set()
    if expr_node is None:
        return result
    candidate = getattr(expr_node, "this", None)
    if isinstance(candidate, exp.Table):
        name = _table_full_name(candidate)
        if name:
            result.add(name)
        return result
    expressions = getattr(expr_node, "expressions", None) or []
    for item in expressions:
        if isinstance(item, exp.Table):
            name = _table_full_name(item)
            if name:
                result.add(name)
    return result


def _has_subquery(tree: Any) -> bool:
    return any(True for _ in tree.find_all(exp.Subquery)) if tree else False


def _table_full_name(table: Any) -> str:
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
