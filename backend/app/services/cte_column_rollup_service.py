"""Recursive CTE / subquery column lineage rollup service.

Expands immediate dependencies like:
    output.S2D <- search_result.click_uv, search_result.show_uv
into root dependencies like:
    output.S2D <- dwd_xx.orig_device_id, ...

Uses DFS because one output column may depend on many input columns.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from app.domain.cte_rollup_models import (
    ColumnDependency, ColumnRef, DerivedRelationSchema,
    LineageDiagnostic, LineagePath, RollupResult, normalize_identifier,
)

DERIVED_KINDS = {"cte", "subquery"}


@dataclass
class _ExpandState:
    output: ColumnRef
    visited: Set[Tuple[str, str, str, str]]
    path: List[ColumnRef]
    transform_types: List[str]


class CteColumnRollupService:
    """Expand derived-relation columns to physical root table columns."""

    def __init__(self, derived_schemas: Dict[str, DerivedRelationSchema]):
        self.derived_schemas = {
            normalize_identifier(name): schema for name, schema in derived_schemas.items()
        }
        self.diagnostics: List[LineageDiagnostic] = []

    def rollup(self, immediate_dependencies: List[ColumnDependency]) -> RollupResult:
        root_dependencies: List[ColumnDependency] = []
        all_paths: List[LineagePath] = []
        self.diagnostics = []

        for dep in immediate_dependencies:
            roots: List[ColumnRef] = []
            paths: List[LineagePath] = []

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
    ) -> Tuple[List[ColumnRef], List[LineagePath]]:
        key = ref.lookup_key()
        if key in state.visited:
            diag = LineageDiagnostic(
                code="CYCLIC_DERIVED_RELATION",
                message=f"Cyclic derived lineage detected at {ref.display()}.",
                relation_name=ref.relation_name,
                column_name=ref.column_name,
            )
            self.diagnostics.append(diag)
            return [ref], [self._make_path(state, ref, [diag])]

        visited = set(state.visited)
        visited.add(key)

        if ref.relation_kind not in DERIVED_KINDS:
            return [ref], [self._make_path(state, ref, [])]

        schema = self.derived_schemas.get(ref.relation_key)
        if schema is None:
            diag = LineageDiagnostic(
                code="UNKNOWN_DERIVED_RELATION",
                message=f"Derived relation schema not found: {ref.relation_name}.",
                relation_name=ref.relation_name,
                column_name=ref.column_name,
            )
            self.diagnostics.append(diag)
            return [ref], [self._make_path(state, ref, [diag])]

        inner_dep = schema.get_dependency(ref.column_name)
        if inner_dep is None:
            diag = LineageDiagnostic(
                code="UNKNOWN_DERIVED_COLUMN",
                message=f"Column {ref.column_name} not found in derived relation {ref.relation_name}.",
                relation_name=ref.relation_name,
                column_name=ref.column_name,
            )
            self.diagnostics.append(diag)
            return [ref], [self._make_path(state, ref, [diag])]

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

        roots: List[ColumnRef] = []
        paths: List[LineagePath] = []
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
        self, state: _ExpandState, root: ColumnRef,
        diagnostics: List[LineageDiagnostic],
    ) -> LineagePath:
        return LineagePath(
            output=state.output,
            root=root,
            path=state.path,
            transform_types=state.transform_types,
            diagnostics=diagnostics,
        )

    def _dedupe_refs(self, refs: List[ColumnRef]) -> List[ColumnRef]:
        seen: Set[Tuple[str, str, str, str]] = set()
        result: List[ColumnRef] = []
        for ref in refs:
            key = ref.lookup_key()
            if key not in seen:
                seen.add(key)
                result.append(ref)
        return result
