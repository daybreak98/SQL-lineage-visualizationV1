"""
Reference implementation: analyze_controller unified orchestration patch

This file is intentionally written as integration pseudocode because the actual project
may use existing Pydantic models, dataclasses, and helper functions.

Goal:
- Remove controller-level CTE / non-CTE big branching.
- Keep service responsibilities separated.
"""

from __future__ import annotations

from typing import Any

# Existing project imports should be used in the real file:
# from app.services.sql_parse_service import parse_sql
# from app.services.query_structure_service import analyze_query_structure
# from app.services.cte_structure_service import analyze_cte_structure
# from app.services.table_structure_service import analyze_table_structure
# from app.services.name_resolver import resolve_column_lineage_names
# from app.services.graph_builder import (
#     build_cte_structure_graph,
#     build_table_structure_graph,
#     build_column_lineage_graph,
#     merge_graphs,
#     validate_graph,
# )
# from app.services.source_location_service import build_source_locations
# from app.services.source_location_targets import extract_source_location_targets_from_graph
# from app.domain.lineage_context import LineageResolveContext


def analyze_unified_orchestrator(request: Any) -> Any:
    """Reference orchestration for POST /api/sql/analyze.

    Replace the current CTE / non-CTE big branch in analyze_controller with this shape.
    """
    sql = request.sql
    dialect = getattr(request, "dialect", None) or "spark"
    options = getattr(request, "options", None) or {}

    # 1. Parse once.
    parse_result = parse_sql(sql=sql, dialect=dialect, options=options)  # type: ignore[name-defined]
    diagnostics = list(getattr(parse_result, "diagnostics", []) or [])

    if not getattr(parse_result, "success", True):
        return _assemble_result(  # type: ignore[name-defined]
            parse_result=parse_result,
            graph_view_model=None,
            source_locations={},
            diagnostics=diagnostics,
            capabilities={
                "cte_structure_lineage": False,
                "cte_final_select_column_lineage": False,
                "cte_end_to_end_column_lineage": False,
            },
        )

    tree = parse_result.tree

    # 2. Analyze structure once.
    structure = analyze_query_structure(tree)  # type: ignore[name-defined]
    diagnostics.extend(getattr(structure, "diagnostics", []) or [])

    # 3. Load metadata only for physical tables. Do not load CTE names.
    metadata = _load_metadata(sorted(structure.physical_table_names))  # type: ignore[name-defined]

    # 4. Build resolver context.
    context = LineageResolveContext(  # type: ignore[name-defined]
        cte_names=structure.cte_names,
        final_select_source_names=structure.final_select_source_names,
        physical_table_names=structure.physical_table_names,
        resolve_scope="final_select" if structure.has_cte else "full_query",
        allow_cte=structure.has_cte,
        allow_subquery=False,
    )

    # 5. Resolve column lineage for both CTE and non-CTE queries through the same API.
    lineage_result = resolve_column_lineage_names(  # type: ignore[name-defined]
        tree=tree,
        metadata=metadata,
        context=context,
    )
    diagnostics.extend(getattr(lineage_result, "diagnostics", []) or [])

    # 6. Build structure graphs conditionally, but do not branch the whole pipeline.
    graphs = []

    if structure.has_cte:
        cte_structure = analyze_cte_structure(tree)  # type: ignore[name-defined]
        diagnostics.extend(getattr(cte_structure, "diagnostics", []) or [])
        graphs.append(build_cte_structure_graph(cte_structure))  # type: ignore[name-defined]
    else:
        table_structure = analyze_table_structure(tree)  # type: ignore[name-defined]
        diagnostics.extend(getattr(table_structure, "diagnostics", []) or [])
        graphs.append(build_table_structure_graph(table_structure))  # type: ignore[name-defined]

    # Always build column lineage graph if possible.
    lineages = getattr(lineage_result, "lineages", []) or []
    if lineages:
        graphs.append(build_column_lineage_graph(lineages))  # type: ignore[name-defined]

    graph = merge_graphs("lineage", *graphs)  # type: ignore[name-defined]
    graph_validation_diagnostics = validate_graph(graph)  # type: ignore[name-defined]
    if graph_validation_diagnostics:
        diagnostics.extend(graph_validation_diagnostics)

    # 7. SourceLocation targets should come from final graph nodes.
    target_entities = extract_source_location_targets_from_graph(graph)  # type: ignore[name-defined]
    source_locations = build_source_locations(  # type: ignore[name-defined]
        sql=sql,
        target_entities=target_entities,
    )

    # 8. Make capability boundaries explicit.
    capabilities = {
        "cte_structure_lineage": bool(structure.has_cte),
        "cte_final_select_column_lineage": bool(structure.has_cte and lineages),
        "cte_end_to_end_column_lineage": False,
        "source_location_output_column": True,
        "source_location_physical_table": True,
        "source_location_cte": True,
    }

    return _assemble_result(  # type: ignore[name-defined]
        parse_result=parse_result,
        graph_view_model=graph,
        source_locations=source_locations,
        diagnostics=diagnostics,
        capabilities=capabilities,
    )
