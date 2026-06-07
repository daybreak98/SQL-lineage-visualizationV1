"""Lineage resolution context — replaces boolean flags in name_resolver.

Encodes: CTE names, physical tables, final SELECT sources, resolve scope.
"""
from dataclasses import dataclass, field
from typing import Literal, Set

ResolveScope = Literal["full_query", "final_select"]


@dataclass(frozen=True)
class LineageResolveContext:
    cte_names: Set[str] = field(default_factory=set)
    final_select_source_names: Set[str] = field(default_factory=set)
    physical_table_names: Set[str] = field(default_factory=set)
    resolve_scope: ResolveScope = "full_query"
    allow_cte: bool = False
    allow_subquery: bool = False

    @classmethod
    def default(cls) -> "LineageResolveContext":
        return cls()

    @property
    def has_cte(self) -> bool:
        return bool(self.cte_names) or self.allow_cte

    def is_cte_name(self, name: str) -> bool:
        return _norm_name(name) in {_norm_name(x) for x in self.cte_names}

    def is_physical_table_name(self, name: str) -> bool:
        return _norm_name(name) in {_norm_name(x) for x in self.physical_table_names}


def _norm_name(name: str) -> str:
    return name.strip('`" ').lower()
