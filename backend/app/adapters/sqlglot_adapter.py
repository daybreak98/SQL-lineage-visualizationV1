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


def extract_output_fields_from_tree(
    tree: Expression,
    dialect: str = "spark",
    placeholder_map: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    def restore_placeholders(text: str) -> str:
        if not placeholder_map:
            return text
        restored = text
        for placeholder, raw_text in sorted(placeholder_map.items(), key=lambda item: len(item[0]), reverse=True):
            restored = restored.replace(placeholder, raw_text)
        return restored

    output_fields: list[dict[str, str]] = []

    for col_expr in tree.selects:
        alias = col_expr.alias or ""

        if alias:
            inner = col_expr.this.sql(dialect=dialect) if hasattr(col_expr, "this") else col_expr.sql(dialect=dialect)
            output_fields.append(
                {
                    "name": alias,
                    "display_name": alias,
                    "expression": restore_placeholders(inner),
                    "source_type": "expression",
                }
            )
        else:
            raw = restore_placeholders(col_expr.sql(dialect=dialect))
            is_simple_column = isinstance(col_expr, Column)
            output_fields.append(
                {
                    "name": raw,
                    "display_name": raw,
                    "expression": raw,
                    "source_type": "unknown" if is_simple_column else "expression",
                }
            )

    return output_fields


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

    return ParseResult(success=True, output_fields=extract_output_fields_from_tree(tree, dialect=dialect), tree=tree)
