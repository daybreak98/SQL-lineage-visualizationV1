"""Domain models for recursive CTE column lineage rollup.

Independent from SQLGlot — usable in service layer and testable without parser.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

RelationKind = Literal["table", "cte", "subquery", "output", "unknown"]
TransformType = Literal["projection", "alias", "aggregate", "window",
                          "case_when", "expression", "constant", "star", "unknown"]
ConfidenceLevel = Literal["high", "medium", "low"]
DiagnosticLevel = Literal["info", "warning", "error"]


def normalize_identifier(value: Optional[str]) -> str:
    if not value:
        return ""
    return value.strip().strip("`").strip('"').lower()


@dataclass(frozen=True)
class ColumnRef:
    relation_name: str
    column_name: str
    relation_kind: RelationKind = "unknown"
    scope_id: str = ""
    table_alias: Optional[str] = None
    entity_id: Optional[str] = None

    @property
    def relation_key(self) -> str:
        return normalize_identifier(self.relation_name)

    @property
    def column_key(self) -> str:
        return normalize_identifier(self.column_name)

    def lookup_key(self) -> Tuple[str, str, str, str]:
        return (self.scope_id or "", self.relation_kind, self.relation_key, self.column_key)

    def display(self) -> str:
        prefix = f"{self.relation_name}." if self.relation_name else ""
        return f"{prefix}{self.column_name}"


@dataclass
class LineageDiagnostic:
    code: str
    message: str
    level: DiagnosticLevel = "warning"
    relation_name: Optional[str] = None
    column_name: Optional[str] = None


@dataclass
class ColumnDependency:
    output: ColumnRef
    inputs: List[ColumnRef]
    transform_type: TransformType = "projection"
    expression: Optional[str] = None
    confidence: ConfidenceLevel = "high"
    diagnostics: List[LineageDiagnostic] = field(default_factory=list)

    def is_constant(self) -> bool:
        return not self.inputs and self.transform_type == "constant"


@dataclass
class DerivedRelationSchema:
    relation_name: str
    relation_kind: RelationKind
    output_columns: Dict[str, ColumnDependency] = field(default_factory=dict)
    scope_id: str = ""

    @property
    def relation_key(self) -> str:
        return normalize_identifier(self.relation_name)

    def add_dependency(self, dependency: ColumnDependency) -> None:
        self.output_columns[dependency.output.column_key] = dependency

    def get_dependency(self, column_name: str) -> Optional[ColumnDependency]:
        return self.output_columns.get(normalize_identifier(column_name))


@dataclass
class LineagePath:
    output: ColumnRef
    root: ColumnRef
    path: List[ColumnRef]
    transform_types: List[TransformType] = field(default_factory=list)
    diagnostics: List[LineageDiagnostic] = field(default_factory=list)


@dataclass
class RollupResult:
    root_dependencies: List[ColumnDependency]
    lineage_paths: List[LineagePath]
    diagnostics: List[LineageDiagnostic] = field(default_factory=list)
