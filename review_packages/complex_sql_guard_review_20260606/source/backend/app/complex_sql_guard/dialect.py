from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QuoteRules:
    double_quote_mode: str = "string"
    backtick_mode: str = "identifier"


@dataclass(frozen=True)
class FunctionRegistry:
    transparent_functions: tuple[str, ...] = (
        "cast",
        "coalesce",
        "nvl",
        "upper",
        "lower",
        "trim",
    )
    regex_functions: tuple[str, ...] = ("regexp_extract", "regexp_replace")
    json_functions: tuple[str, ...] = ("get_json_object", "json_tuple", "from_json")


@dataclass(frozen=True)
class UdtfRegistry:
    row_expanding_functions: tuple[str, ...] = ("explode", "posexplode", "inline")


@dataclass(frozen=True)
class TemplateRules:
    variable_prefixes: tuple[str, ...] = ("${", "#{")
    freemarker_prefixes: tuple[str, ...] = ("<#", "</#")


@dataclass(frozen=True)
class IdentifierRules:
    allow_backtick_identifier: bool = True
    allow_chinese_alias: bool = True


@dataclass(frozen=True)
class DialectProfile:
    name: str
    parser_dialect: str
    quote_rules: QuoteRules = field(default_factory=QuoteRules)
    function_registry: FunctionRegistry = field(default_factory=FunctionRegistry)
    udtf_registry: UdtfRegistry = field(default_factory=UdtfRegistry)
    template_rules: TemplateRules = field(default_factory=TemplateRules)
    identifier_rules: IdentifierRules = field(default_factory=IdentifierRules)
    lateral_view_enabled: bool = True


DIALECTS = {
    "generic": DialectProfile(name="generic", parser_dialect="spark"),
    "hive": DialectProfile(name="hive", parser_dialect="hive"),
    "spark": DialectProfile(name="spark", parser_dialect="spark"),
}


def get_dialect_profile(name: str | None) -> DialectProfile:
    key = (name or "spark").lower()
    return DIALECTS.get(key, DIALECTS["spark"])

