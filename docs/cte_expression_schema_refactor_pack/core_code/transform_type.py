"""Transform type inference for ExpressionAnalyzer metrics."""

from __future__ import annotations


def infer_transform_type(metric) -> str:
    """
    Infer transform_type from ExpressionMetric-like object.

    Expected metric attributes:
        - expression: str
        - aggregate_functions: list[str]
        - depends_on: list[str]
    """
    expression = (getattr(metric, "expression", None) or "").lower()
    aggregate_functions = [f.lower() for f in (getattr(metric, "aggregate_functions", None) or [])]
    depends_on = getattr(metric, "depends_on", None) or []

    if aggregate_functions:
        if any(op in expression for op in ["+", "-", "*", "/"]):
            return "aggregate_expression"
        return "aggregate"

    if expression.startswith("case ") or " case " in expression:
        return "case_when"

    if " over " in expression:
        return "window"

    if not depends_on:
        if _looks_like_constant(expression):
            return "constant"
        if _looks_like_system_function(expression):
            return "system_function"
        if "count(*)" in expression or "count(1)" in expression:
            return "aggregate"
        return "unknown_expression"

    if "(" in expression and ")" in expression:
        return "function"

    if any(op in expression for op in ["+", "-", "*", "/"]):
        return "expression"

    return "expression"


def infer_dependency_type(metric, transform_type: str) -> str:
    expression = (getattr(metric, "expression", None) or "").lower().replace(" ", "")
    depends_on = getattr(metric, "depends_on", None) or []

    if depends_on:
        return "column"

    if "count(*)" in expression or "count(1)" in expression:
        return "relation_rowset"

    if transform_type in {"constant", "system_function"}:
        return "none"

    return "unknown"


def _looks_like_constant(expression: str) -> bool:
    expression = expression.strip().strip("'").strip('"')
    if expression in {"true", "false", "null"}:
        return True
    try:
        float(expression)
        return True
    except ValueError:
        return False


def _looks_like_system_function(expression: str) -> bool:
    expr = expression.strip().lower()
    return expr in {
        "current_date",
        "current_timestamp",
        "now()",
        "current_date()",
        "current_timestamp()",
    }
