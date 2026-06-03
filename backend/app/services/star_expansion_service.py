from __future__ import annotations

from dataclasses import dataclass, field

from sqlglot import exp

from app.domain import diagnostics_model as diag_codes
from app.domain.lineage_model import SimpleColumnLineage
from app.models import Diagnostic


@dataclass
class StarExpansionResult:
    lineages: list[SimpleColumnLineage] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    unsupported_features: list[str] = field(default_factory=list)


def expand_star_items(
    select_items: list[exp.Expression],
    source_table_names: list[str],
    alias_to_table: dict[str, str],
    columns_by_table: dict[str, list[dict[str, object]]],
) -> StarExpansionResult:
    result = StarExpansionResult()

    for item in select_items:
        is_star, qualifier = _detect_star(item)
        if not is_star:
            continue

        if qualifier:
            _expand_qualified_star(result, qualifier, alias_to_table, columns_by_table)
        else:
            _expand_unqualified_star(result, source_table_names, alias_to_table, columns_by_table)

    return result


def _detect_star(item: exp.Expression) -> tuple[bool, str | None]:
    if isinstance(item, exp.Star):
        return True, None
    if isinstance(item, exp.Column) and isinstance(item.this, exp.Star):
        return True, item.table or None
    return False, None


def _expand_qualified_star(
    result: StarExpansionResult,
    qualifier: str,
    alias_to_table: dict[str, str],
    columns_by_table: dict[str, list[dict[str, object]]],
) -> None:
    resolved = alias_to_table.get(qualifier)
    if resolved is None:
        result.diagnostics.append(
            Diagnostic(
                code=diag_codes.UNKNOWN_TABLE_ALIAS,
                level="warning",
                message=f"Table qualifier {qualifier} in {qualifier}.* cannot be resolved.",
            )
        )
        return
    _add_lineages_for_table(result, resolved, columns_by_table)


def _expand_unqualified_star(
    result: StarExpansionResult,
    source_table_names: list[str],
    alias_to_table: dict[str, str],
    columns_by_table: dict[str, list[dict[str, object]]],
) -> None:
    resolved_tables: list[str] = []
    missing: list[str] = []

    for tname in source_table_names:
        if columns_by_table.get(tname):
            resolved_tables.append(tname)
        else:
            missing.append(tname)

    if missing:
        result.diagnostics.append(
            Diagnostic(
                code=diag_codes.METADATA_MISSING,
                level="warning",
                message=f"No metadata for table(s): {', '.join(missing)}. "
                        f"Import metadata to enable SELECT * expansion.",
            )
        )
        result.unsupported_features.append("metadata_missing")

    if not resolved_tables and not missing:
        result.diagnostics.append(
            Diagnostic(
                code=diag_codes.SELECT_STAR_METADATA_REQUIRED,
                level="warning",
                message="SELECT * expansion requires table metadata. No metadata available.",
            )
        )
        result.unsupported_features.append("select_star")
        return

    for tname in resolved_tables:
        _add_lineages_for_table(result, tname, columns_by_table)

    if not resolved_tables and missing:
        result.diagnostics.append(
            Diagnostic(
                code=diag_codes.SELECT_STAR_METADATA_REQUIRED,
                level="warning",
                message="SELECT * expansion requires metadata for all source tables.",
            )
        )
        result.unsupported_features.append("select_star")


def _add_lineages_for_table(
    result: StarExpansionResult,
    table_name: str,
    columns_by_table: dict[str, list[dict[str, object]]],
) -> None:
    columns = columns_by_table.get(table_name)
    if not columns:
        result.diagnostics.append(
            Diagnostic(
                code=diag_codes.METADATA_MISSING,
                level="warning",
                message=f"No metadata for table {table_name}.",
            )
        )
        return

    for col in columns:
        col_name = str(col.get("name", ""))
        if col_name:
            result.lineages.append(
                SimpleColumnLineage(
                    source_table=table_name,
                    source_column=col_name,
                    output_column=col_name,
                )
            )
