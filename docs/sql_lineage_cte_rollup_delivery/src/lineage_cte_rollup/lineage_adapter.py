"""Adapters between legacy SimpleColumnLineage and the new dependency model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import ColumnDependency, ColumnRef


@dataclass
class SimpleColumnLineageCompat:
    """Minimal shape compatible with the existing SimpleColumnLineage.

    Replace this class with your project's real SimpleColumnLineage import.
    """

    source_table: str
    source_column: str
    output_column: str


def simple_to_dependency(
    lineage: SimpleColumnLineageCompat,
    output_relation_name: str = "final",
    source_relation_kind: str = "unknown",
) -> ColumnDependency:
    return ColumnDependency(
        output=ColumnRef(
            relation_name=output_relation_name,
            column_name=lineage.output_column,
            relation_kind="output",
        ),
        inputs=[
            ColumnRef(
                relation_name=lineage.source_table,
                column_name=lineage.source_column,
                relation_kind=source_relation_kind,  # caller can mark cte/table by scope
            )
        ],
        transform_type="projection",
    )


def dependencies_to_simple(
    dependencies: Iterable[ColumnDependency],
) -> list[SimpleColumnLineageCompat]:
    """Flatten root dependencies back to legacy simple lineage rows.

    This preserves the external response shape while allowing multiple root
    sources for one output column.
    """
    rows: list[SimpleColumnLineageCompat] = []
    for dep in dependencies:
        for ref in dep.inputs:
            rows.append(
                SimpleColumnLineageCompat(
                    source_table=ref.relation_name,
                    source_column=ref.column_name,
                    output_column=dep.output.column_name,
                )
            )
    return rows
