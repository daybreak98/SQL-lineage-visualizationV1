"""Compatibility helpers for sqlglot AST argument names.

sqlglot has used both keyword-style names such as ``from_`` and SQL-style
names such as ``from`` / ``with`` across dialects and versions. Keep access
centralized so lineage code does not silently miss a FROM clause again.
"""
from __future__ import annotations

from typing import Any


def get_from_expression(select_node: Any) -> Any:
    if select_node is None:
        return None
    args = getattr(select_node, "args", {}) or {}
    return args.get("from_") or args.get("from")


def get_with_expression(select_node: Any) -> Any:
    if select_node is None:
        return None
    args = getattr(select_node, "args", {}) or {}
    return args.get("with_") or args.get("with")
