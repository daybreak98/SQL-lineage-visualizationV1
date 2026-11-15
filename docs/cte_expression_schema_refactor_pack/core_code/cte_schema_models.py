"""
Reference domain models for CTE schema building.

These classes are intentionally small and dependency-free. If the project already
has equivalent models, reuse existing classes and only add missing fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

RelationKind = Literal["cte", "table", "subquery", "unknown"]
DependencyOrigin = Literal["name_resolver", "expression_analyzer", "merged", "manual"]


@dataclass(frozen=True)
class RelationRef:
    """A visible relation in a SELECT scope."""

    relation_name: str
    relation_kind: RelationKind
    alias: Optional[str] = None

    @property
    def key(self) -> str:
        return self.relation_name.lower()


@dataclass(frozen=True)
class ColumnRef:
    """A resolvable upstream column reference for rollup."""

    relation_name: Optional[str]
    column_name: str
    relation_kind: RelationKind
    qualifier: Optional[str] = None

    @property
    def relation_key(self) -> Optional[str]:
        return self.relation_name.lower() if self.relation_name else None

    @property
    def column_key(self) -> str:
        return self.column_name.lower()


@dataclass
class ColumnDependency:
    """Output column dependency in one CTE schema."""

    output_column: str
    input_columns: list[ColumnRef] = field(default_factory=list)
    transform_type: str = "direct"
    expression: Optional[str] = None
    dependency_type: str = "column"  # column | relation_rowset | none | unknown
    confidence: float = 1.0
    origin: DependencyOrigin = "name_resolver"

    @property
    def output_key(self) -> str:
        return self.output_column.lower()


@dataclass
class CteSchemaBuildResult:
    """Return object for build_cte_schemas."""

    schemas: dict[str, dict[str, ColumnDependency]]
    diagnostics: list[object] = field(default_factory=list)
