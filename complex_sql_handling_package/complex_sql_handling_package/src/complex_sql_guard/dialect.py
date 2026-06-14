from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DialectProfile:
    name: str
    parser_dialect: str
    double_quote_mode: str = "string"
    backtick_mode: str = "identifier"
    template_enabled: bool = True
    lateral_view_enabled: bool = True
    raw_string_enabled: bool = True


DIALECTS = {
    "hive": DialectProfile(name="hive", parser_dialect="hive"),
    "spark": DialectProfile(name="spark", parser_dialect="spark"),
}


def get_dialect_profile(name: str | None) -> DialectProfile:
    key = (name or "spark").lower()
    return DIALECTS.get(key, DIALECTS["spark"])
