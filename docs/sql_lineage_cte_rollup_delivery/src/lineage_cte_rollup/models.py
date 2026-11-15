"""Domain models for recursive CTE column lineage rollup.

These models are intentionally independent from SQLGlot so they can be used
inside the service layer and tested without a parser dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


RelationKind = Literal["table", "cte", "subquery", "output", "unknown"]
TransformType = Literal[
    "projection",
    "alias",
    "aggregate",
    "window",
    "case_when",
    "expression",
    "constant",
    "star",
    "unknown",
]
ConfidenceLevel = Literal["high", "medium", "low"]
DiagnosticLevel = Literal["info", "warning", "error"]


def normalize_identifier(value: str | None) -> str:
    """Normalize identifier for lookup keys.

    Keep display names in the original field, but use this normalized key for
    case-insensitive lookup. Backticks are removed because Hive/Spark aliases
    often contain Chinese display names quoted by backticks.
    """
    if not value:
        return ""
    return value.strip().strip("`").strip('"').lower()


@dataclass(frozen=True)
class ColumnRef:
    """A column reference in a physical or derived relation."""

    relation_name: str
    column_name: str
    relation_kind: RelationKind = "unknown"
    scope_id: str = ""
    table_alias: str | None = None
    entity_id: str | None = None

    @property
    def relation_key(self) -> str:
        return normalize_identifier(self.relation_name)

    @property
    def column_key(self) -> str:
        return normalize_identifier(self.column_name)

    def lookup_key(self) -> tuple[str, str, str, str]:
        return (
            self.scope_id or "",
            self.relation_kind,
            self.relation_key,
            self.column_key,
        )

    def display(self) -> str:
        prefix = f"{self.relation_name}." if self.relation_name else ""
        return f"{prefix}{self.column_name}"


@dataclass
class LineageDiagnostic:
    code: str
    message: str
    level: DiagnosticLevel = "warning"
    relation_name: str | None = None
    column_name: str | None = None


@dataclass
class ColumnDependency:
    """Dependency from one output column to zero or more input columns."""

    output: ColumnRef
    inputs: list[ColumnRef]
    transform_type: TransformType = "projection"
    expression: str | None = None
    confidence: ConfidenceLevel = "high"
    diagnostics: list[LineageDiagnostic] = field(default_factory=list)

    def is_constant(self) -> bool:
        return not self.inputs and self.transform_type == "constant"


@dataclass
class DerivedRelationSchema:
    """Output schema of a CTE / subquery / derived table."""

    relation_name: str
    relation_kind: RelationKind
    output_columns: dict[str, ColumnDependency] = field(default_factory=dict)
    scope_id: str = ""

    @property
    def relation_key(self) -> str:
        return normalize_identifier(self.relation_name)

    def add_dependency(self, dependency: ColumnDependency) -> None:
        self.output_columns[dependency.output.column_key] = dependency

    def get_dependency(self, column_name: str) -> ColumnDependency | None:
        return self.output_columns.get(normalize_identifier(column_name))


@dataclass
class LineagePath:
    """Full path from an output column to one root input column."""

    output: ColumnRef
    root: ColumnRef
    path: list[ColumnRef]
    transform_types: list[TransformType] = field(default_factory=list)
    diagnostics: list[LineageDiagnostic] = field(default_factory=list)


@dataclass
class RollupResult:
    root_dependencies: list[ColumnDependency]
    lineage_paths: list[LineagePath]
    diagnostics: list[LineageDiagnostic] = field(default_factory=list)
