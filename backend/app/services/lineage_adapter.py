"""Adapters between SimpleColumnLineage and ColumnDependency model."""
from typing import Iterable, List

from app.domain.cte_rollup_models import ColumnDependency, ColumnRef
from app.domain.lineage_model import SimpleColumnLineage


def simple_to_dependency(
    lineage: SimpleColumnLineage,
    output_relation_name: str = "final",
    source_relation_kind: str = "unknown",
) -> ColumnDependency:
    """Convert one SimpleColumnLineage row to ColumnDependency."""
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
                relation_kind=source_relation_kind,
            )
        ],
        transform_type="projection",
    )


def dependencies_to_simple(
    dependencies: Iterable[ColumnDependency],
) -> List[SimpleColumnLineage]:
    """Flatten root ColumnDependency back to SimpleColumnLineage list.

    One output column with N root sources produces N SimpleColumnLineage rows.
    """
    rows: List[SimpleColumnLineage] = []
    for dep in dependencies:
        for ref in dep.inputs:
            rows.append(
                SimpleColumnLineage(
                    source_table=ref.relation_name,
                    source_column=ref.column_name,
                    output_column=dep.output.column_name,
                )
            )
    return rows
