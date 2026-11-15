"""Per-parse source provenance for the supported SQLGlot JSON path builder."""

import sqlglot
from sqlglot import exp
from sqlglot.dialects import Dialect
from sqlglot.tokens import TokenType


def parse_with_json_path_positions(sql, dialect_name):
    """Parse once, preserving verified original path literals before conversion.

    Only whole-input parsing uses this helper. Recovery and macro slices keep
    their existing parser, so no relative span is mistaken for an absolute one.
    """
    if sqlglot.__version__ != "30.31.0" or dialect_name not in {"hive", "spark"}:
        return sqlglot.parse(sql, read=dialect_name)
    dialect = Dialect.get_or_raise(dialect_name)
    parser_type = dialect.parser_class
    original_builder = parser_type.FUNCTIONS.get("GET_JSON_OBJECT")
    if not callable(original_builder):
        return dialect.parse(sql)
    tokens = dialect.tokenize(sql)
    strings = {(t.start, t.end): t for t in tokens if t.token_type == TokenType.STRING}

    def build(args, dialect):
        literal = args[1] if len(args) > 1 else None
        result = original_builder(args, dialect=dialect)
        if (type(literal) is exp.Literal and literal.is_string
                and type(result.expression) is exp.JSONPath):
            start, end = literal.meta.get("start"), literal.meta.get("end")
            if (type(start) is int and type(end) is int and 0 <= start <= end < len(sql)):
                token = strings.get((start, end))
                if token is not None and token.text == literal.this:
                    # A private metadata key does not change ordinary evidence
                    # positions or claim positions for individual JSONPath keys.
                    result.expression.meta["json_path_position"] = {
                        "start": start, "end": end + 1,
                        "line": token.line, "column_end": token.col,
                    }
        return result

    class PositionedParser(parser_type):
        FUNCTIONS = {**parser_type.FUNCTIONS, "GET_JSON_OBJECT": build}

    return PositionedParser(dialect=dialect).parse(tokens, sql)
