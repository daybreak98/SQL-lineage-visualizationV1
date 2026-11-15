"""Integration example for AnalysisOrchestrator.

This is not meant to be copied blindly. Use it as a patch guide for your current
project structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cte_column_rollup_service import CteColumnRollupService
from .derived_relation_schema_builder import DerivedRelationSchemaBuilder, SelectDependencyResolver
from .models import ColumnDependency, DerivedRelationSchema, RollupResult


@dataclass
class LineageResolveArtifacts:
    derived_schemas: dict[str, DerivedRelationSchema]
    immediate_dependencies: list[ColumnDependency]
    rollup_result: RollupResult


class AnalysisOrchestratorCteRollupMixin:
    """Mixin-style example to be merged into your AnalysisOrchestrator."""

    dependency_resolver: SelectDependencyResolver

    def resolve_lineage_with_cte_rollup(
        self,
        ast: Any,
        final_select_node: Any,
        ordered_ctes: list[tuple[str, Any]],
    ) -> LineageResolveArtifacts:
        # 1. Build CTE schemas in order.
        schema_builder = DerivedRelationSchemaBuilder(self.dependency_resolver)
        schema_result = schema_builder.build_from_ordered_ctes(ordered_ctes)

        # 2. Resolve final SELECT one-hop dependencies.
        immediate_dependencies = self.dependency_resolver.resolve_select_dependencies(
            select_node=final_select_node,
            output_relation_name="final",
            derived_schemas=schema_result.schemas,
        )

        # 3. Roll up CTE/subquery fields to physical roots.
        rollup_service = CteColumnRollupService(schema_result.schemas)
        rollup_result = rollup_service.rollup(immediate_dependencies)
        rollup_result.diagnostics.extend(schema_result.diagnostics)

        return LineageResolveArtifacts(
            derived_schemas=schema_result.schemas,
            immediate_dependencies=immediate_dependencies,
            rollup_result=rollup_result,
        )
