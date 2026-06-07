"""Recursive CTE / subquery column lineage rollup service.

The service expands immediate dependencies like:

    output.S2D <- search_result.click_uv, search_result.show_uv

into root dependencies like:

    output.S2D <- default.dwd_ihotel_flow_app_searchlist_di.orig_device_id, ...

It uses DFS because one output column may depend on many input columns.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    ColumnDependency,
    ColumnRef,
    DerivedRelationSchema,
    LineageDiagnostic,
    LineagePath,
    RollupResult,
    normalize_identifier,
)


DERIVED_KINDS = {"cte", "subquery"}


@dataclass
class _ExpandState:
    output: ColumnRef
    visited: set[tuple[str, str, str, str]]
    path: list[ColumnRef]
    transform_types: list[str]


class CteColumnRollupService:
    """Expand derived-relation columns to physical root table columns."""

    def __init__(self, derived_schemas: dict[str, DerivedRelationSchema]):
        # Key by normalized relation name. For projects with nested scopes, this
        # can be upgraded to key by (scope_id, relation_name).
        self.derived_schemas = {
            normalize_identifier(name): schema for name, schema in derived_schemas.items()
        }
        self.diagnostics: list[LineageDiagnostic] = []

    def rollup(self, immediate_dependencies: list[ColumnDependency]) -> RollupResult:
        """Roll up all immediate dependencies.

        Returns root_dependencies and lineage_paths. The output field is kept as
        the final output column; inputs are physical root columns when known.
        """
        root_dependencies: list[ColumnDependency] = []
        all_paths: list[LineagePath] = []
        self.diagnostics = []

        for dep in immediate_dependencies:
            roots: list[ColumnRef] = []
            paths: list[LineagePath] = []

            if dep.is_constant():
                root_dependencies.append(dep)
                continue

            for input_ref in dep.inputs:
                expanded_roots, expanded_paths = self._expand_ref(
                    input_ref,
                    _ExpandState(
                        output=dep.output,
                        visited=set(),
                        path=[dep.output, input_ref],
                        transform_types=[dep.transform_type],
                    ),
                )
                roots.extend(expanded_roots)
                paths.extend(expanded_paths)

            roots = self._dedupe_refs(roots)
            root_dependencies.append(
                ColumnDependency(
                    output=dep.output,
                    inputs=roots,
                    transform_type=dep.transform_type,
                    expression=dep.expression,
                    confidence=dep.confidence,
                    diagnostics=dep.diagnostics.copy(),
                )
            )
            all_paths.extend(paths)

        return RollupResult(
            root_dependencies=root_dependencies,
            lineage_paths=all_paths,
            diagnostics=self.diagnostics.copy(),
        )

    def _expand_ref(
        self,
        ref: ColumnRef,
        state: _ExpandState,
    ) -> tuple[list[ColumnRef], list[LineagePath]]:
        key = ref.lookup_key()
        if key in state.visited:
            diagnostic = LineageDiagnostic(
                code="CYCLIC_DERIVED_RELATION",
                message=f"Cyclic derived lineage detected at {ref.display()}.",
                relation_name=ref.relation_name,
                column_name=ref.column_name,
            )
            self.diagnostics.append(diagnostic)
            return [ref], [self._make_path(state, ref, [diagnostic])]

        visited = set(state.visited)
        visited.add(key)

        if ref.relation_kind not in DERIVED_KINDS:
            return [ref], [self._make_path(state, ref, [])]

        schema = self.derived_schemas.get(ref.relation_key)
        if schema is None:
            diagnostic = LineageDiagnostic(
                code="UNKNOWN_DERIVED_RELATION",
                message=f"Derived relation schema not found: {ref.relation_name}.",
                relation_name=ref.relation_name,
                column_name=ref.column_name,
            )
            self.diagnostics.append(diagnostic)
            return [ref], [self._make_path(state, ref, [diagnostic])]

        inner_dep = schema.get_dependency(ref.column_name)
        if inner_dep is None:
            diagnostic = LineageDiagnostic(
                code="UNKNOWN_DERIVED_COLUMN",
                message=f"Column {ref.column_name} not found in derived relation {ref.relation_name}.",
                relation_name=ref.relation_name,
                column_name=ref.column_name,
            )
            self.diagnostics.append(diagnostic)
            return [ref], [self._make_path(state, ref, [diagnostic])]

        if inner_dep.is_constant():
            return [], [
                LineagePath(
                    output=state.output,
                    root=inner_dep.output,
                    path=state.path + [inner_dep.output],
                    transform_types=state.transform_types + [inner_dep.transform_type],
                    diagnostics=inner_dep.diagnostics.copy(),
                )
            ]

        roots: list[ColumnRef] = []
        paths: list[LineagePath] = []
        for inner_input in inner_dep.inputs:
            child_roots, child_paths = self._expand_ref(
                inner_input,
                _ExpandState(
                    output=state.output,
                    visited=visited,
                    path=state.path + [inner_input],
                    transform_types=state.transform_types + [inner_dep.transform_type],
                ),
            )
            roots.extend(child_roots)
            paths.extend(child_paths)

        return self._dedupe_refs(roots), paths

    def _make_path(
        self,
        state: _ExpandState,
        root: ColumnRef,
        diagnostics: list[LineageDiagnostic],
    ) -> LineagePath:
        return LineagePath(
            output=state.output,
            root=root,
            path=state.path,
            transform_types=state.transform_types,
            diagnostics=diagnostics,
        )

    def _dedupe_refs(self, refs: list[ColumnRef]) -> list[ColumnRef]:
        seen: set[tuple[str, str, str, str]] = set()
        result: list[ColumnRef] = []
        for ref in refs:
            key = ref.lookup_key()
            if key not in seen:
                seen.add(key)
                result.append(ref)
        return result
