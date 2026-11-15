"""
Resolve ExpressionAnalyzer depends_on values into ColumnRef objects.

This is the most important part of the refactor: do not directly write
ExpressionAnalyzer.depends_on into CTE schemas. First resolve them through the
current SELECT scope, existing CTE schemas, and metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from cte_schema_models import ColumnRef, RelationRef, ColumnDependency
from cte_scope_resolver import SelectScope


@dataclass
class SimpleDiagnostic:
    code: str
    level: str
    message: str
    context: dict = field(default_factory=dict)


def resolve_expression_dependency_column(
    raw_dep: str,
    scope: SelectScope,
    cte_schemas: dict[str, dict[str, ColumnDependency]],
    metadata: dict[str, list[str]],
) -> tuple[list[ColumnRef], list[SimpleDiagnostic]]:
    """
    Convert one ExpressionAnalyzer dependency into ColumnRef(s).

    Supported raw_dep forms:
        - a.search_request_uid
        - search_base.search_request_uid
        - search_request_uid
    """
    raw_dep = (raw_dep or "").strip()
    if not raw_dep:
        return [], []

    if "." in raw_dep:
        qualifier, column_name = raw_dep.split(".", 1)
        relation = scope.resolve_qualifier(qualifier)
        if not relation:
            return [], [
                SimpleDiagnostic(
                    code="UNKNOWN_TABLE_ALIAS",
                    level="warning",
                    message=f"Cannot resolve qualifier '{qualifier}' for expression dependency '{raw_dep}'.",
                    context={"dependency": raw_dep, "qualifier": qualifier},
                )
            ]
        return [
            ColumnRef(
                relation_name=relation.relation_name,
                column_name=column_name,
                relation_kind=relation.relation_kind,
                qualifier=qualifier,
            )
        ], []

    # Bare column: resolve by visible relations and available schemas/metadata.
    return _resolve_bare_column(
        column_name=raw_dep,
        scope=scope,
        cte_schemas=cte_schemas,
        metadata=metadata,
    )


def _resolve_bare_column(
    column_name: str,
    scope: SelectScope,
    cte_schemas: dict[str, dict[str, ColumnDependency]],
    metadata: dict[str, list[str]],
) -> tuple[list[ColumnRef], list[SimpleDiagnostic]]:
    visible = scope.visible_relations

    if len(visible) == 1:
        relation = visible[0]
        return [
            ColumnRef(
                relation_name=relation.relation_name,
                column_name=column_name,
                relation_kind=relation.relation_kind,
                qualifier=None,
            )
        ], []

    candidates = []
    for relation in visible:
        if _relation_has_column(relation, column_name, cte_schemas, metadata):
            candidates.append(relation)

    if len(candidates) == 1:
        relation = candidates[0]
        return [
            ColumnRef(
                relation_name=relation.relation_name,
                column_name=column_name,
                relation_kind=relation.relation_kind,
                qualifier=None,
            )
        ], []

    if len(candidates) > 1:
        return [], [
            SimpleDiagnostic(
                code="AMBIGUOUS_COLUMN",
                level="warning",
                message=f"Bare expression dependency '{column_name}' is ambiguous across visible relations.",
                context={
                    "column": column_name,
                    "candidate_relations": [r.relation_name for r in candidates],
                },
            )
        ]

    return [], [
        SimpleDiagnostic(
            code="UNKNOWN_COLUMN",
            level="warning",
            message=f"Cannot resolve bare expression dependency '{column_name}' in current SELECT scope.",
            context={"column": column_name, "visible_relations": [r.relation_name for r in visible]},
        )
    ]


def _relation_has_column(
    relation: RelationRef,
    column_name: str,
    cte_schemas: dict[str, dict[str, ColumnDependency]],
    metadata: dict[str, list[str]],
) -> bool:
    relation_key = relation.relation_name.lower()
    column_key = column_name.lower()

    if relation.relation_kind == "cte":
        schema = cte_schemas.get(relation_key, {})
        return column_key in {k.lower() for k in schema.keys()}

    # physical table metadata may be keyed in original or lower-case form.
    cols = metadata.get(relation.relation_name) or metadata.get(relation_key) or []
    return column_key in {c.lower() for c in cols}


def deduplicate_column_refs(refs: Iterable[ColumnRef]) -> list[ColumnRef]:
    seen = set()
    result = []
    for ref in refs:
        key = (ref.relation_key, ref.column_key, ref.relation_kind)
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result
