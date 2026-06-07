"""DerivedRelationSchema builder — builds CTE and inline subquery output column schemas.

Uses name_resolver + ExpressionDependencyExtractor to extract column→source mappings.
Handles select * expansion for relations that already have schemas.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from sqlglot import exp

from app.domain.cte_rollup_models import (
    ColumnDependency, ColumnRef, DerivedRelationSchema, LineageDiagnostic,
)
from app.services.expression_dependency_extractor import (
    ExpressionDependencyExtractor, build_scope_from_cte_body,
)
from app.services.name_resolver import resolve_column_lineage_names


@dataclass
class CTESelectNode:
    cte_name: str
    select_node: exp.Select


@dataclass
class BuildDerivedSchemasResult:
    schemas: Dict[str, DerivedRelationSchema] = field(default_factory=dict)
    diagnostics: List[LineageDiagnostic] = field(default_factory=list)


def extract_cte_select_nodes(tree: Any) -> List[CTESelectNode]:
    nodes: List[CTESelectNode] = []
    with_expr = tree.args.get("with_") or tree.args.get("with")
    if with_expr is None:
        return nodes
    for cte_expr in getattr(with_expr, "expressions", []):
        name = getattr(cte_expr, "alias_or_name", None)
        if not name:
            continue
        inner_select = cte_expr.find(exp.Select)
        if inner_select is not None:
            nodes.append(CTESelectNode(cte_name=name, select_node=inner_select))
    return nodes


def build_cte_schemas(
    tree: Any, dialect: str = "spark",
) -> BuildDerivedSchemasResult:
    cte_nodes = extract_cte_select_nodes(tree)
    schemas: Dict[str, DerivedRelationSchema] = {}
    cte_names: Set[str] = {n.cte_name.lower().strip("`") for n in cte_nodes}

    # Phase 1: Build CTE schemas in WITH order (earlier CTEs visible to later ones)
    for cte_node in cte_nodes:
        schema = _build_single_schema(
            cte_node.select_node, cte_node.cte_name, "cte", cte_names, schemas)
        schemas[schema.relation_key] = schema

    # Phase 2: Build schemas for inline FROM/JOIN subqueries
    # These reference CTEs already built in Phase 1
    _build_inline_subquery_schemas(cte_nodes, schemas, cte_names)

    return BuildDerivedSchemasResult(schemas=schemas)


def _build_inline_subquery_schemas(
    cte_nodes: List[CTESelectNode],
    schemas: Dict[str, DerivedRelationSchema],
    cte_names: Set[str],
    visited: Optional[Set[str]] = None,
    max_depth: int = 3,
) -> None:
    if visited is None:
        visited = set()
    if max_depth <= 0:
        return

    new_schemas: Dict[str, DerivedRelationSchema] = {}

    for cte_node in cte_nodes:
        for subquery, alias in _extract_from_subqueries(cte_node.select_node):
            key = alias.lower().strip("`")
            if key in schemas or key in new_schemas or key in visited:
                continue
            visited.add(key)
            try:
                schema = _build_single_schema(subquery, alias, "subquery", cte_names, schemas)
                new_schemas[key] = schema
            except Exception:
                pass

    schemas.update(new_schemas)


def _extract_from_subqueries(
    select_node: exp.Select,
) -> List[tuple]:
    """Extract (inner_select, alias) pairs from FROM/JOIN subqueries."""
    pairs: List[tuple] = []
    from_expr = select_node.args.get("from_") or select_node.args.get("from")
    if from_expr is not None and isinstance(from_expr.this, exp.Subquery):
        alias = from_expr.this.alias or from_expr.alias
        inner = from_expr.this.this  # Subquery.this → Select
        if alias and isinstance(inner, exp.Select):
            pairs.append((inner, alias))
    for join in select_node.args.get("joins") or []:
        if isinstance(join.this, exp.Subquery):
            alias = join.this.alias or join.alias
            inner = join.this.this
            if alias and isinstance(inner, exp.Select):
                pairs.append((inner, alias))
    return pairs


def _build_single_schema(
    select_node: exp.Select,
    relation_name: str,
    relation_kind: str,
    cte_names: Set[str],
    existing_schemas: Dict[str, DerivedRelationSchema],
) -> DerivedRelationSchema:
    schema = DerivedRelationSchema(relation_name=relation_name, relation_kind=relation_kind)

    # Path A: name_resolver for simple column projections
    inner_result = resolve_column_lineage_names(
        "", "spark", tree=select_node, is_cte_context=False)

    resolved_columns: Set[str] = set()
    for lineage in inner_result.lineages:
        src = lineage.source_table.lower().strip("`")
        source_kind = "cte" if src in cte_names else "table"
        dep = ColumnDependency(
            output=ColumnRef(relation_name, lineage.output_column, relation_kind),
            inputs=[ColumnRef(lineage.source_table, lineage.source_column, source_kind)],
            transform_type="projection",
        )
        schema.add_dependency(dep)
        resolved_columns.add(lineage.output_column.lower().strip("`"))

    # Path B: ExpressionDependencyExtractor for complex expressions
    _extract_complex_dependencies(select_node, relation_name, relation_kind,
                                   cte_names, resolved_columns, schema)

    # Path C: select * expansion from known schemas
    _expand_star_from_schemas(select_node, relation_name, relation_kind,
                               existing_schemas, resolved_columns, schema)

    return schema


def _extract_complex_dependencies(
    select_node: exp.Select, relation_name: str, relation_kind: str,
    cte_names: Set[str], resolved_columns: Set[str],
    schema: DerivedRelationSchema,
) -> None:
    try:
        scope = build_scope_from_cte_body(select_node, cte_names)
        extractor = ExpressionDependencyExtractor()
        for projection in select_node.selects:
            output_name = (
                getattr(projection, "alias_or_name", None)
                or getattr(projection, "name", None))
            if not output_name:
                continue
            if output_name.lower().strip("`") in resolved_columns:
                continue
            dep = extractor.dependency_from_projection(projection, relation_name, scope)
            if dep and dep.inputs:
                for inp in dep.inputs:
                    rn = inp.relation_name.lower().strip("`")
                    if rn in cte_names:
                        inp.__dict__["relation_kind"] = "cte"
                schema.add_dependency(dep)
    except Exception:
        pass


def _expand_star_from_schemas(
    select_node: exp.Select, relation_name: str, relation_kind: str,
    existing_schemas: Dict[str, DerivedRelationSchema],
    resolved_columns: Set[str], schema: DerivedRelationSchema,
) -> None:
    """Handle select * by expanding from known source schemas."""
    has_star = any(
        isinstance(item, exp.Star)
        or (isinstance(item, exp.Column) and isinstance(item.this, exp.Star))
        for item in select_node.selects
    )
    if not has_star:
        return

    # Get source table names from FROM/JOIN
    from_tables = _get_from_table_names(select_node)
    for table_name in from_tables:
        key = table_name.lower().strip("`")
        src_schema = existing_schemas.get(key)
        if src_schema is None:
            continue
        for col_name, src_dep in src_schema.output_columns.items():
            if col_name in resolved_columns:
                continue
            dep = ColumnDependency(
                output=ColumnRef(relation_name, src_dep.output.column_name, relation_kind),
                inputs=[ColumnRef(
                    inp.relation_name, inp.column_name, inp.relation_kind,
                ) for inp in src_dep.inputs],
                transform_type=src_dep.transform_type,
                expression=src_dep.expression,
            )
            schema.add_dependency(dep)


def _get_from_table_names(select_node: exp.Select) -> List[str]:
    names: List[str] = []
    from_expr = select_node.args.get("from_") or select_node.args.get("from")
    if from_expr is not None and isinstance(from_expr.this, exp.Table):
        parts = [p for p in [from_expr.this.catalog, from_expr.this.db, from_expr.this.name] if p]
        names.append(".".join(parts) if parts else (from_expr.this.name or ""))
    for join in select_node.args.get("joins") or []:
        if isinstance(join.this, exp.Table):
            parts = [p for p in [join.this.catalog, join.this.db, join.this.name] if p]
            names.append(".".join(parts) if parts else (join.this.name or ""))
    return names
