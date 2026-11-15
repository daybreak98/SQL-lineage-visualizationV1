"""
Reference patch for build_cte_schemas.

This file is intentionally written as a transplantable implementation sketch.
Adjust imports and adapter functions according to the actual project layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from cte_schema_models import ColumnDependency, CteSchemaBuildResult
from cte_scope_resolver import extract_select_scope
from expression_dependency_resolver import (
    SimpleDiagnostic,
    deduplicate_column_refs,
    resolve_expression_dependency_column,
)
from transform_type import infer_dependency_type, infer_transform_type


# -----------------------------------------------------------------------------
# Adapter placeholders: replace these with project-native implementations.
# -----------------------------------------------------------------------------


def iter_cte_definitions_in_order(tree):
    """
    Yield (cte_name, cte_body_expr) in SQL definition order.

    Replace with existing CTE iterator if the project already has one.
    """
    raise NotImplementedError("Wire this function to existing cte_structure_service helpers.")


def extract_select_from_cte_body(cte_body):
    """Return inner SELECT expression from CTE body."""
    return cte_body


def resolve_column_lineage_names_for_cte_body(inner_select, metadata, context):
    """
    Call existing name_resolver for one CTE body.

    Expected return:
        result.lineages: list with source_table/source_column/output_column
        result.diagnostics: list
    """
    raise NotImplementedError("Call existing name_resolver.resolve_column_lineage_names(...).")


def analyze_select_expressions(inner_select):
    """
    Call existing ExpressionAnalyzer().analyze_select(inner_select).

    Expected metric attributes:
        name: output column name
        expression: expression SQL string
        depends_on: list[str]
        aggregate_functions: list[str]
    """
    raise NotImplementedError("Call existing ExpressionAnalyzer().analyze_select(...).")


def make_lineage_context_for_cte_body(cte_name: str, cte_names: set[str]):
    """Build or adapt LineageResolveContext for name_resolver."""
    return {
        "current_cte_name": cte_name,
        "cte_names": cte_names,
        "resolve_scope": "cte_body",
        "allow_cte": True,
    }


# -----------------------------------------------------------------------------
# Core conversion and merge logic.
# -----------------------------------------------------------------------------


def convert_name_resolver_lineages_to_schema(cte_name: str, lineages: list, scope) -> dict[str, ColumnDependency]:
    """
    Convert SimpleColumnLineage-like objects to schema entries.

    Expected lineage attributes:
        source_table, source_column, output_column
    """
    schema: dict[str, ColumnDependency] = {}

    for lin in lineages:
        output_col = getattr(lin, "output_column", None)
        source_table = getattr(lin, "source_table", None)
        source_column = getattr(lin, "source_column", None)
        if not output_col or not source_column:
            continue

        relation = scope.resolve_qualifier(source_table) if source_table else None
        relation_name = relation.relation_name if relation else source_table
        relation_kind = relation.relation_kind if relation else "unknown"

        from cte_schema_models import ColumnRef

        schema[output_col.lower()] = ColumnDependency(
            output_column=output_col,
            input_columns=[
                ColumnRef(
                    relation_name=relation_name,
                    column_name=source_column,
                    relation_kind=relation_kind,
                    qualifier=source_table,
                )
            ],
            transform_type="direct",
            expression=None,
            dependency_type="column",
            confidence=1.0,
            origin="name_resolver",
        )

    return schema


def merge_expression_metrics_into_schema(
    schema: dict[str, ColumnDependency],
    expr_metrics: list,
    scope,
    cte_schemas: dict[str, dict[str, ColumnDependency]],
    metadata: dict[str, list[str]],
) -> list[SimpleDiagnostic]:
    """
    Fill schema gaps with ExpressionAnalyzer metrics.

    Principle:
        name_resolver wins for columns it already handled.
        ExpressionAnalyzer only supplements missing output columns.
    """
    diagnostics: list[SimpleDiagnostic] = []

    for metric in expr_metrics:
        output_col = getattr(metric, "name", None)
        if not output_col:
            continue
        output_key = output_col.lower()

        # Do not override name_resolver result.
        if output_key in schema:
            if not schema[output_key].expression:
                schema[output_key].expression = getattr(metric, "expression", None)
            continue

        input_refs = []
        for dep in getattr(metric, "depends_on", None) or []:
            refs, diags = resolve_expression_dependency_column(
                raw_dep=dep,
                scope=scope,
                cte_schemas=cte_schemas,
                metadata=metadata,
            )
            input_refs.extend(refs)
            diagnostics.extend(diags)

        input_refs = deduplicate_column_refs(input_refs)
        transform_type = infer_transform_type(metric)
        dependency_type = infer_dependency_type(metric, transform_type)

        confidence = _confidence_for_expression_dependency(input_refs, dependency_type, diagnostics)

        schema[output_key] = ColumnDependency(
            output_column=output_col,
            input_columns=input_refs,
            transform_type=transform_type,
            expression=getattr(metric, "expression", None),
            dependency_type=dependency_type,
            confidence=confidence,
            origin="expression_analyzer",
        )

    return diagnostics


def _confidence_for_expression_dependency(input_refs, dependency_type: str, diagnostics: list[SimpleDiagnostic]) -> float:
    if input_refs:
        return 0.85
    if dependency_type in {"relation_rowset", "none"}:
        return 0.8
    return 0.45


# -----------------------------------------------------------------------------
# Main patch function.
# -----------------------------------------------------------------------------


def build_cte_schemas_with_expression_dependencies(tree, metadata: dict[str, list[str]], cte_names: set[str]) -> CteSchemaBuildResult:
    """
    Enhanced CTE schema builder.

    This should replace or wrap the existing build_cte_schemas function.
    It preserves the original simple-column path and adds ExpressionAnalyzer as
    a supplementary path for complex expressions.
    """
    cte_schemas: dict[str, dict[str, ColumnDependency]] = {}
    diagnostics: list[object] = []

    for cte_name, cte_body in iter_cte_definitions_in_order(tree):
        inner_select = extract_select_from_cte_body(cte_body)
        scope = extract_select_scope(inner_select, cte_names=cte_names)

        # Path A: original name_resolver for simple projections.
        context = make_lineage_context_for_cte_body(cte_name=cte_name, cte_names=cte_names)
        name_result = resolve_column_lineage_names_for_cte_body(
            inner_select=inner_select,
            metadata=metadata,
            context=context,
        )
        diagnostics.extend(getattr(name_result, "diagnostics", []) or [])

        schema = convert_name_resolver_lineages_to_schema(
            cte_name=cte_name,
            lineages=getattr(name_result, "lineages", []) or [],
            scope=scope,
        )

        # Path B: ExpressionAnalyzer for complex expressions.
        expr_metrics = analyze_select_expressions(inner_select)
        expr_diagnostics = merge_expression_metrics_into_schema(
            schema=schema,
            expr_metrics=expr_metrics,
            scope=scope,
            cte_schemas=cte_schemas,
            metadata=metadata,
        )
        diagnostics.extend(expr_diagnostics)

        cte_schemas[cte_name.lower()] = schema

    return CteSchemaBuildResult(schemas=cte_schemas, diagnostics=diagnostics)
