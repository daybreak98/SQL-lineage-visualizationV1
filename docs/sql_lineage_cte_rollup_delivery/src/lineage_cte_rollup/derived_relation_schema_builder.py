"""Derived relation schema builder skeleton.

In the existing project, prefer integrating this idea with the current
ScopeResolver / NameResolver instead of building a parallel parser pipeline.

Responsibilities:
- Build a schema for each CTE / FROM subquery.
- Each schema maps output column name to ColumnDependency.
- CTEs must be processed in dependency order because later CTEs can reference
  earlier CTEs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import ColumnDependency, DerivedRelationSchema, LineageDiagnostic


class SelectDependencyResolver(Protocol):
    """Adapter protocol over the existing name_resolver/expression analyzer."""

    def resolve_select_dependencies(
        self,
        select_node: Any,
        output_relation_name: str,
        derived_schemas: dict[str, DerivedRelationSchema],
    ) -> list[ColumnDependency]:
        ...


@dataclass
class BuildDerivedSchemasResult:
    schemas: dict[str, DerivedRelationSchema]
    diagnostics: list[LineageDiagnostic] = field(default_factory=list)


class DerivedRelationSchemaBuilder:
    """Build CTE/subquery output schemas using an injected resolver."""

    def __init__(self, resolver: SelectDependencyResolver):
        self.resolver = resolver

    def build_from_ordered_ctes(self, ordered_ctes: list[tuple[str, Any]]) -> BuildDerivedSchemasResult:
        """Build schemas from CTEs already ordered as they appear in WITH.

        SQL WITH semantics allow later CTEs to reference earlier CTEs. If your
        dialect allows out-of-order references, replace this with a dependency
        topological sort.
        """
        schemas: dict[str, DerivedRelationSchema] = {}
        diagnostics: list[LineageDiagnostic] = []

        for cte_name, cte_select_node in ordered_ctes:
            try:
                dependencies = self.resolver.resolve_select_dependencies(
                    select_node=cte_select_node,
                    output_relation_name=cte_name,
                    derived_schemas=schemas,
                )
            except Exception as exc:  # keep analysis partial instead of crashing
                diagnostics.append(
                    LineageDiagnostic(
                        code="CTE_SCHEMA_BUILD_FAILED",
                        message=f"Failed to build schema for CTE {cte_name}: {exc}",
                        level="warning",
                        relation_name=cte_name,
                    )
                )
                continue

            schema = DerivedRelationSchema(
                relation_name=cte_name,
                relation_kind="cte",
            )
            for dep in dependencies:
                schema.add_dependency(dep)
            schemas[schema.relation_key] = schema

        return BuildDerivedSchemasResult(schemas=schemas, diagnostics=diagnostics)
