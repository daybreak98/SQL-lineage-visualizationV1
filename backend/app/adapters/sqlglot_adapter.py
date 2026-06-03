from __future__ import annotations

import sqlglot
from sqlglot.errors import ParseError as SqlglotParseError
from sqlglot.expressions import Column, Expression


class ParseResult:
    def __init__(
        self,
        success: bool,
        output_fields: list[dict[str, str]],
        error_message: str | None = None,
        tree: Expression | None = None,
    ):
        self.success = success
        self.output_fields = output_fields
        self.error_message = error_message
        self.tree = tree


def parse_and_extract(sql: str, dialect: str = "spark") -> ParseResult:
    try:
        tree = sqlglot.parse_one(sql, dialect=dialect)
    except SqlglotParseError as e:
        return ParseResult(
            success=False,
            output_fields=[],
            error_message=f"SQL parse error: {e}",
            tree=None,
        )

    output_fields: list[dict[str, str]] = []

    for col_expr in tree.selects:
        alias = col_expr.alias or ""  # sqlglot 无别名时返回 ""，不是 None

        if alias:
            inner = col_expr.this.sql(dialect=dialect) if hasattr(col_expr, "this") else col_expr.sql(dialect=dialect)
            output_fields.append(
                {
                    "name": alias,
                    "display_name": alias,
                    "expression": inner,
                    "source_type": "expression",
                }
            )
        else:
            raw = col_expr.sql(dialect=dialect)
            is_simple_column = isinstance(col_expr, Column)
            output_fields.append(
                {
                    "name": raw,
                    "display_name": raw,
                    "expression": raw,
                    "source_type": "unknown" if is_simple_column else "expression",
                }
            )

    return ParseResult(success=True, output_fields=output_fields, tree=tree)
