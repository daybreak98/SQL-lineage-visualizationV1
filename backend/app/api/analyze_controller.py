from __future__ import annotations

import re

from fastapi import APIRouter

from app.models import AnalyzeRequest, AnalysisResult, DiagnosticsReport, GraphViewModel
from app.repositories import metadata_repository as meta_repo
from app.services.cte_structure_service import analyze_cte_structure
from app.services.graph_builder import (
    build_column_lineage_graph,
    build_cte_structure_graph,
    build_expression_graph,
    build_table_structure_graph,
    merge_graphs,
)
from app.services.name_resolver import resolve_column_lineage_names
from app.services.expression_analyzer import ExpressionAnalyzer, metrics_to_semantics_report
from app.services.source_location_service import build_source_locations
from app.services.sql_parse_service import parse_sql
from app.services.table_structure_service import analyze_table_structure

router = APIRouter()


@router.post("/sql/analyze", response_model=AnalysisResult)
async def analyze(request: AnalyzeRequest) -> AnalysisResult:
    parse_result = parse_sql(request.sql, request.dialect, request.options)

    graph_view_model = GraphViewModel()
    diagnostics = list(parse_result.diagnostics)
    stage_statuses = list(parse_result.stage_statuses)
    unsupported_features = list(parse_result.unsupported_features)
    status = parse_result.status
    confidence = dict(parse_result.confidence)
    source_locations: dict[str, object] = {}
    semantics_report_val: dict | None = None

    if parse_result.tree is not None and request.analysis_options.include_graph:
        tree = parse_result.tree

        if _looks_like_cte(request.sql, tree):
            structure_result = analyze_cte_structure(request.sql, request.dialect, tree=tree)
            diagnostics.extend(structure_result.diagnostics)
            stage_statuses.extend(structure_result.stage_statuses)
            unsupported_features.extend(structure_result.unsupported_features)
            status = _merge_status(status, structure_result.status)

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
            status = _merge_status(status, table_structure_result.status)

            source_table_names = _extract_source_table_names(tree)
            metadata = _load_metadata(source_table_names)

            lineage_result = resolve_column_lineage_names(request.sql, request.dialect, tree=tree, metadata=metadata)
            diagnostics.extend(lineage_result.diagnostics)
            stage_statuses.extend(lineage_result.stage_statuses)
            unsupported_features.extend(lineage_result.unsupported_features)
            status = _merge_status(status, lineage_result.status)

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

            # C09: expression analysis
            if request.analysis_options.include_expression_lineage and parse_result.tree is not None:
                analyzer = ExpressionAnalyzer(dialect=request.dialect)
                metrics = analyzer.analyze_select(parse_result.tree)
                if metrics:
                    semantics_report_val = metrics_to_semantics_report(metrics)
                    expr_nodes, expr_edges = build_expression_graph(
                        metrics=[m.to_dict() for m in metrics],
                        existing_nodes=graph_view_model.nodes,
                        existing_edges=graph_view_model.edges,
                    )
                    for n in expr_nodes:
                        graph_view_model.nodes.append(n)
                    for e in expr_edges:
                        graph_view_model.edges.append(e)

        if request.analysis_options.include_source_location:
            target_entities = _target_entities(graph_view_model)
            source_location_result = build_source_locations(request.sql, target_entities=target_entities)
            source_locations = source_location_result.locations
            diagnostics.extend(source_location_result.diagnostics)
            stage_statuses.extend(source_location_result.stage_statuses)

    confidence = _adjust_confidence(confidence, status, unsupported_features)
    confidence_level = _confidence_level_from_scores(confidence, status)
    diagnostics = _dedupe_diagnostics(diagnostics)
    unsupported_features = sorted(set(unsupported_features))

    return _assemble_result(
        request=request,
        status=status,
        confidence_level=confidence_level,
        confidence=confidence,
        elapsed_ms=parse_result.elapsed_ms,
        stage_statuses=stage_statuses,
        diagnostics=diagnostics,
        output_fields=parse_result.output_fields,
        unsupported_features=unsupported_features,
        graph_view_model=graph_view_model,
        source_locations=source_locations,
        normalized_sql=parse_result.normalized_sql,
        analysis_sql=parse_result.analysis_sql,
        sql_text_bundle=parse_result.sql_text_bundle,
        preflight_report=parse_result.preflight_report,
        segments=parse_result.segments,
        parse_attempts=parse_result.parse_attempts,
        capabilities=parse_result.capabilities,
        semantics_report=semantics_report_val,
        summary={
            "node_count": len(graph_view_model.nodes),
            "edge_count": len(graph_view_model.edges),
            "output_field_count": len(parse_result.output_fields),
            "placeholder_count": int(parse_result.capabilities.get("placeholder_count", 0)),
            "segment_count": int(parse_result.capabilities.get("segment_count", 0)),
        },
    )


def _assemble_result(
    request: AnalyzeRequest,
    status: str,
    confidence_level: str,
    confidence: dict[str, float],
    elapsed_ms: int,
    stage_statuses: list[dict[str, object]],
    diagnostics: list,
    output_fields: list,
    unsupported_features: list[str] | None = None,
    graph_view_model: GraphViewModel | None = None,
    source_locations: dict[str, object] | None = None,
    normalized_sql: str | None = None,
    analysis_sql: str | None = None,
    sql_text_bundle: dict[str, object] | None = None,
    preflight_report: dict[str, object] | None = None,
    segments: list[dict[str, object]] | None = None,
    parse_attempts: list[dict[str, object]] | None = None,
    capabilities: dict[str, object] | None = None,
    summary: dict[str, int] | None = None,
    semantics_report: dict | None = None,
) -> AnalysisResult:
    result = AnalysisResult(
        schema_version="0.3.0-c09",
        analysis_id="analysis:c09",
        status=status,
        confidence_level=confidence_level,
        confidence=confidence,
        dialect=request.dialect,
        elapsed_ms=elapsed_ms,
        normalized_sql=normalized_sql,
        analysis_sql=analysis_sql,
        stage_statuses=stage_statuses,
        unsupported_features=unsupported_features or [],
        diagnostics=diagnostics,
        diagnostics_report=DiagnosticsReport(
            diagnostics=diagnostics,
            error_count=sum(1 for diagnostic in diagnostics if diagnostic.level == "error"),
            warning_count=sum(1 for diagnostic in diagnostics if diagnostic.level == "warning"),
            info_count=sum(1 for diagnostic in diagnostics if diagnostic.level == "info"),
        ),
        graph_view_model=graph_view_model or GraphViewModel(),
        output_fields=output_fields,
        source_locations=source_locations or {},
        sql_text_bundle=sql_text_bundle or {},
        preflight_report=preflight_report or {},
        segments=segments or [],
        parse_attempts=parse_attempts or [],
        capabilities=capabilities or {},
        summary=summary or {},
        semantics_report=semantics_report,
    )
    return result


def _looks_like_cte(sql: str, tree=None) -> bool:
    if tree is not None and (tree.args.get("with_") is not None or tree.args.get("with") is not None):
        return True
    stripped = re.sub(r"--[^\n]*", "", sql)
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)
    return stripped.lstrip().lower().startswith("with ")


def _merge_status(*statuses: str) -> str:
    order = {"success": 0, "partial": 1, "failed": 2}
    return max(statuses, key=lambda status: order.get(status, 0))


def _adjust_confidence(
    confidence: dict[str, float],
    status: str,
    unsupported_features: list[str],
) -> dict[str, float]:
    adjusted = dict(confidence)
    if status == "failed":
        adjusted["parse"] = 0.0
        adjusted["lineage"] = 0.0
    elif status == "partial":
        adjusted["lineage"] = min(adjusted.get("lineage", 0.55), 0.55)
    if unsupported_features:
        adjusted["lineage"] = min(adjusted.get("lineage", 0.55), 0.55)
    return adjusted


def _confidence_level_from_scores(confidence: dict[str, float], status: str) -> str:
    if status == "failed":
        return "unknown"
    score = confidence.get("lineage", confidence.get("parse", 0.0))
    if score >= 0.85:
        return "high"
    if score >= 0.6:
        return "medium"
    return "unknown"


def _extract_source_table_names(tree) -> list[str]:
    from sqlglot import exp

    names: list[str] = []
    for table in tree.find_all(exp.Table):
        parts = [part for part in [table.catalog, table.db, table.name] if part]
        name = ".".join(parts) if parts else table.name
        if name not in names:
            names.append(name)
    return names


def _load_metadata(table_names: list[str]) -> dict[str, list[str]]:
    columns_by_table = meta_repo.get_columns_for_tables(table_names)
    result: dict[str, list[str]] = {}
    for table_name in table_names:
        if table_name in columns_by_table:
            result[table_name] = [str(column.get("name", "")) for column in columns_by_table[table_name]]
        else:
            result[table_name] = []
    return result


def _dedupe_diagnostics(diagnostics: list) -> list:
    seen: set[tuple[str, str | None, str]] = set()
    result = []
    for diagnostic in diagnostics:
        key = (diagnostic.code, getattr(diagnostic, "stage", None), diagnostic.message)
        if key in seen:
            continue
        seen.add(key)
        result.append(diagnostic)
    return result


def _output_column_names(graph_view_model: GraphViewModel, output_fields: list) -> list[str]:
    names = [
        str(node.get("label", ""))
        for node in graph_view_model.nodes
        if node.get("node_type") in {"output_column", "output_field"}
    ]
    if names:
        return names
    return [str(field.name) for field in output_fields if getattr(field, "name", "")]


def _target_entities(graph_view_model: GraphViewModel) -> list[dict[str, str]]:
    type_map = {
        "output_column": "output_column",
        "output_field": "output_column",
        "physical_column": "output_column",
        "table": "physical_table",
        "physical_table": "physical_table",
        "cte": "cte",
        "subquery": "cte",
    }
    entities: list[dict[str, str]] = []
    seen: set[str] = set()
    for node in graph_view_model.nodes:
        ntype = str(node.get("node_type", ""))
        entity_type = type_map.get(ntype)
        if entity_type is None:
            continue
        label = str(node.get("label", "")).split(".")[-1]
        if not label:
            continue
        entity_id = f"{entity_type}:{label}"
        key = f"{entity_id}::{entity_type}"
        if key not in seen:
            seen.add(key)
            entities.append({"entityId": entity_id, "entityType": entity_type})
    return entities

