from fastapi import APIRouter

from app.models import AnalyzeRequest, AnalysisResult, DiagnosticsReport, GraphViewModel
from app.repositories import metadata_repository as meta_repo
from app.services.cte_structure_service import analyze_cte_structure
from app.services.graph_builder import (
    build_column_lineage_graph,
    build_cte_structure_graph,
    build_table_structure_graph,
    merge_graphs,
)
from app.services.name_resolver import resolve_column_lineage_names
from app.services.sql_parse_service import parse_sql
from app.services.table_structure_service import analyze_table_structure

router = APIRouter()


@router.post("/sql/analyze", response_model=AnalysisResult)
async def analyze(request: AnalyzeRequest) -> AnalysisResult:
    parse_result = parse_sql(request.sql, request.dialect)

    if not parse_result.success:
        return _assemble_result(
            request=request,
            status="failed",
            confidence_level="unknown",
            elapsed_ms=parse_result.elapsed_ms,
            stage_statuses=parse_result.stage_statuses,
            diagnostics=parse_result.diagnostics,
            output_fields=parse_result.output_fields,
        )

    tree = parse_result.tree
    graph_view_model = GraphViewModel()
    diagnostics = list(parse_result.diagnostics)
    stage_statuses = list(parse_result.stage_statuses)
    unsupported_features: list[str] = []
    status = "success"
    confidence_level = "high"

    if request.analysis_options.include_graph:
        if _looks_like_cte(request.sql):
            structure_result = analyze_cte_structure(request.sql, request.dialect, tree=tree)
            diagnostics.extend(structure_result.diagnostics)
            stage_statuses.extend(structure_result.stage_statuses)
            unsupported_features.extend(structure_result.unsupported_features)
            status = structure_result.status
            confidence_level = structure_result.confidence_level

            if structure_result.nodes:
                graph = build_cte_structure_graph(structure_result)
                graph_view_model = GraphViewModel(**graph.to_dict())
                stage_statuses.append(
                    {
                        "stage": "graph_build",
                        "status": "success",
                        "elapsed_ms": 0,
                        "diagnostic_codes": [],
                        "message": "GraphViewModel built from CTE structure dependencies.",
                    }
                )
        else:
            table_structure_result = analyze_table_structure(request.sql, request.dialect, tree=tree)
            diagnostics.extend(table_structure_result.diagnostics)
            stage_statuses.extend(table_structure_result.stage_statuses)
            unsupported_features.extend(table_structure_result.unsupported_features)

            source_table_names = _extract_source_table_names(tree)
            metadata = _load_metadata(source_table_names)

            lineage_result = resolve_column_lineage_names(request.sql, request.dialect, tree=tree, metadata=metadata)
            diagnostics.extend(lineage_result.diagnostics)
            stage_statuses.extend(lineage_result.stage_statuses)
            unsupported_features.extend(lineage_result.unsupported_features)

            status = "partial" if (
                table_structure_result.status == "partial" or lineage_result.status == "partial"
            ) else lineage_result.status
            confidence_level = "high" if status == "success" else "unknown"

            graphs = []
            if table_structure_result.nodes:
                graphs.append(build_table_structure_graph(table_structure_result))
            if lineage_result.lineages:
                graphs.append(build_column_lineage_graph(lineage_result.lineages))

            if graphs:
                graph = merge_graphs("table", *graphs)
                graph_view_model = GraphViewModel(**graph.to_dict())
                stage_statuses.append(
                    {
                        "stage": "graph_build",
                        "status": "success",
                        "elapsed_ms": 0,
                        "diagnostic_codes": [],
                        "message": "GraphViewModel built from table structure and column lineage.",
                    }
                )

    return _assemble_result(
        request=request,
        status=status,
        confidence_level=confidence_level,
        elapsed_ms=parse_result.elapsed_ms,
        stage_statuses=stage_statuses,
        diagnostics=diagnostics,
        output_fields=parse_result.output_fields,
        unsupported_features=unsupported_features,
        graph_view_model=graph_view_model,
        summary={
            "node_count": len(graph_view_model.nodes),
            "edge_count": len(graph_view_model.edges),
            "output_field_count": len(parse_result.output_fields),
        },
    )


def _assemble_result(
    request: AnalyzeRequest,
    status: str,
    confidence_level: str,
    elapsed_ms: int,
    stage_statuses: list[dict[str, object]],
    diagnostics: list,
    output_fields: list,
    unsupported_features: list[str] | None = None,
    graph_view_model: GraphViewModel | None = None,
    summary: dict[str, int] | None = None,
) -> AnalysisResult:
    return AnalysisResult(
        schema_version="0.3.0-c05",
        analysis_id="analysis:c05",
        status=status,
        confidence_level=confidence_level,
        dialect=request.dialect,
        elapsed_ms=elapsed_ms,
        stage_statuses=stage_statuses,
        unsupported_features=unsupported_features or [],
        diagnostics_report=DiagnosticsReport(
            diagnostics=diagnostics,
            error_count=sum(1 for d in diagnostics if d.level == "error"),
            warning_count=sum(1 for d in diagnostics if d.level == "warning"),
            info_count=sum(1 for d in diagnostics if d.level == "info"),
        ),
        graph_view_model=graph_view_model or GraphViewModel(),
        output_fields=output_fields,
        summary=summary or {},
    )


def _looks_like_cte(sql: str) -> bool:
    return sql.lstrip().lower().startswith("with ")


def _extract_source_table_names(tree) -> list[str]:
    from sqlglot import exp
    names: list[str] = []
    for table in tree.find_all(exp.Table):
        parts = [p for p in [table.catalog, table.db, table.name] if p]
        name = ".".join(parts) if parts else table.name
        if name not in names:
            names.append(name)
    return names


def _load_metadata(table_names: list[str]) -> dict[str, list[str]]:
    columns_by_table = meta_repo.get_columns_for_tables(table_names)
    result: dict[str, list[str]] = {}
    for tname in table_names:
        if tname in columns_by_table:
            result[tname] = [str(c.get("name", "")) for c in columns_by_table[tname]]
        else:
            result[tname] = []  # table requested but no metadata found
    return result
