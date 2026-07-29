"""DerivedRelationSchema builder.

Uses name_resolver + ExpressionDependencyExtractor to extract column-source mappings.
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
from app.services.lateral_view_dependency_extractor import (
    extract_lateral_view_dependencies,
)
from app.services.name_resolver import resolve_column_lineage_names
from app.services.sqlglot_compat import (
    get_from_expression,
    get_with_expression,
    is_set_operation,
)


@dataclass
class DerivedSelectNode:
    relation_name: str
    select_node: exp.Query
    relation_kind: str = "cte"


CTESelectNode = DerivedSelectNode


@dataclass
class BuildDerivedSchemasResult:
    schemas: Dict[str, DerivedRelationSchema] = field(default_factory=dict)
    diagnostics: List[LineageDiagnostic] = field(default_factory=list)


def extract_cte_select_nodes(tree: Any) -> List[DerivedSelectNode]:
    nodes: List[DerivedSelectNode] = []
    with_expr = get_with_expression(tree)
    if with_expr is None:
        return nodes
    for cte_expr in getattr(with_expr, "expressions", []):
        name = getattr(cte_expr, "alias_or_name", None)
        if not name:
            continue
        query = cte_expr.this
        if isinstance(query, exp.Subquery):
            query = query.this
        if isinstance(query, exp.Query):
            nodes.append(DerivedSelectNode(
                relation_name=name,
                select_node=query,
                relation_kind="cte",
            ))
    return nodes


def build_derived_relation_schemas(
    tree: Any, dialect: str = "spark",
) -> BuildDerivedSchemasResult:
    cte_nodes = extract_cte_select_nodes(tree)
    schemas: Dict[str, DerivedRelationSchema] = {}
    cte_names: Set[str] = {n.relation_name.lower().strip("`") for n in cte_nodes}

    # Phase 1: Build CTE schemas in WITH order so earlier CTEs are visible later.
    for cte_node in cte_nodes:
        schema = _build_single_schema(
            cte_node.select_node,
            cte_node.relation_name,
            "cte",
            cte_names,
            schemas,
            dialect,
        )
        schemas[schema.relation_key] = schema

    # Phase 2: Build inline subquery schemas in the final SELECT and CTE bodies.
    select_nodes = [
        select
        for node in cte_nodes
        for select in _query_selects(node.select_node)
    ]
    outer_select = _outer_select(tree)
    if outer_select is not None:
        select_nodes.append(outer_select)
    _build_inline_subquery_schemas(select_nodes, schemas, cte_names, dialect=dialect)

    return BuildDerivedSchemasResult(schemas=schemas)


def build_cte_schemas(
    tree: Any, dialect: str = "spark",
) -> BuildDerivedSchemasResult:
    return build_derived_relation_schemas(tree, dialect)


def _build_inline_subquery_schemas(
    select_nodes: List[exp.Select],
    schemas: Dict[str, DerivedRelationSchema],
    cte_names: Set[str],
    visited: Optional[Set[str]] = None,
    max_depth: int = 16,
    dialect: str = "spark",
) -> None:
    completed = visited if visited is not None else set()
    if max_depth <= 0:
        return
    visiting: Set[str] = set()

    def build_subquery(query: exp.Query, alias: str, depth: int) -> None:
        key = alias.lower().strip("`")
        if key in schemas or key in completed or key in visiting or depth <= 0:
            return

        visiting.add(key)
        try:
            for child_select in _query_selects(query):
                for child_query, child_alias in _extract_from_subqueries(child_select):
                    build_subquery(child_query, child_alias, depth - 1)

            schemas[key] = _build_single_schema(
                query,
                alias,
                "subquery",
                cte_names,
                schemas,
                dialect,
            )
            completed.add(key)
        except Exception:
            completed.add(key)
        finally:
            visiting.discard(key)

    for select_node in select_nodes:
        for subquery, alias in _extract_from_subqueries(select_node):
            build_subquery(subquery, alias, max_depth)


def _extract_from_subqueries(
    select_node: exp.Select,
) -> List[tuple]:
    """Extract (inner_select, alias) pairs from FROM/JOIN subqueries."""
    pairs: List[tuple] = []
    from_expr = get_from_expression(select_node)
    if from_expr is not None and isinstance(from_expr.this, exp.Subquery):
        alias = from_expr.this.alias or from_expr.alias
        inner = from_expr.this.this
        if alias and isinstance(inner, exp.Query):
            pairs.append((inner, alias))
    for join in select_node.args.get("joins") or []:
        if isinstance(join.this, exp.Subquery):
            alias = join.this.alias or join.alias
            inner = join.this.this
            if alias and isinstance(inner, exp.Query):
                pairs.append((inner, alias))
    return pairs


def _outer_select(tree: Any) -> Optional[exp.Select]:
    if isinstance(tree, exp.Select):
        return tree
    this = getattr(tree, "this", None)
    if isinstance(this, exp.Select):
        return this
    found = tree.find(exp.Select) if tree is not None else None
    return found if isinstance(found, exp.Select) else None


def _query_selects(query: exp.Query) -> List[exp.Select]:
    if is_set_operation(query):
        return _query_selects(query.this) + _query_selects(query.expression)
    if isinstance(query, exp.Subquery):
        return _query_selects(query.this)
    return [query] if isinstance(query, exp.Select) else []


def _add_constant_dependencies(
    query: exp.Query,
    relation_name: str,
    relation_kind: str,
    resolved_columns: Set[str],
    schema: DerivedRelationSchema,
) -> None:
    branches = _query_selects(query)
    if not branches:
        return

    for index, first_projection in enumerate(branches[0].selects):
        output_name = first_projection.alias_or_name
        output_key = output_name.lower().strip("`") if output_name else ""
        if not output_key or output_key in resolved_columns:
            continue
        if any(index >= len(branch.selects) for branch in branches):
            continue
        projections = [branch.selects[index] for branch in branches]
        if any(
            projection.find(exp.Column) is not None
            or projection.find(exp.Star) is not None
            for projection in projections
        ):
            continue
        schema.add_dependency(ColumnDependency(
            output=ColumnRef(relation_name, output_name, relation_kind),
            inputs=[],
            transform_type="constant",
            expression=first_projection.sql(),
        ))
        resolved_columns.add(output_key)


def _build_single_schema(
    select_node: exp.Query,
    relation_name: str,
    relation_kind: str,
    cte_names: Set[str],
    existing_schemas: Dict[str, DerivedRelationSchema],
    dialect: str,
) -> DerivedRelationSchema:
    schema = DerivedRelationSchema(relation_name=relation_name, relation_kind=relation_kind)

    # Path A: name_resolver for simple column projections
    inner_result = resolve_column_lineage_names(
        "", dialect, tree=select_node, is_cte_context=False)

    resolved_columns: Set[str] = set()
    grouped_inputs: Dict[str, List[ColumnRef]] = {}
    output_names: Dict[str, str] = {}
    for lineage in inner_result.lineages:
        output_key = lineage.output_column.lower().strip("`")
        src = lineage.source_table.lower().strip("`")
        source_name = lineage.source_table
        if src.startswith("subquery:"):
            source_name = lineage.source_table[len("subquery:"):]
            source_kind = "subquery"
        else:
            source_kind = "cte" if src in cte_names else "table"
        grouped_inputs.setdefault(output_key, []).append(
            ColumnRef(source_name, lineage.source_column, source_kind)
        )
        output_names[output_key] = lineage.output_column

    for output_key, inputs in grouped_inputs.items():
        dep = ColumnDependency(
            output=ColumnRef(relation_name, output_names[output_key], relation_kind),
            inputs=_dedupe_column_refs(inputs),
            transform_type="projection",
        )
        schema.add_dependency(dep)
        resolved_columns.add(output_key)

    _add_constant_dependencies(
        select_node, relation_name, relation_kind, resolved_columns, schema)

    if is_set_operation(select_node):
        return schema

    # Path B: ExpressionDependencyExtractor for complex expressions
    _extract_complex_dependencies(select_node, relation_name, relation_kind,
                                   cte_names, resolved_columns, schema)

    # Path C: select * expansion from known schemas
    _expand_star_from_schemas(select_node, relation_name, relation_kind,
                               existing_schemas, resolved_columns, schema)

    # Path D: LATERAL VIEW output column -> row-expanding expression inputs.
    _apply_lateral_view_dependencies(
        select_node, relation_name, relation_kind, cte_names, resolved_columns, schema)

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


def _dedupe_column_refs(inputs: List[ColumnRef]) -> List[ColumnRef]:
    seen = set()
    result: List[ColumnRef] = []
    for ref in inputs:
        key = ref.lookup_key()
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _apply_lateral_view_dependencies(
    select_node: exp.Select, relation_name: str, relation_kind: str,
    cte_names: Set[str], resolved_columns: Set[str],
    schema: DerivedRelationSchema,
) -> None:
    scope = build_scope_from_cte_body(select_node, cte_names)
    grouped_inputs: Dict[str, List[ColumnRef]] = {}
    output_names: Dict[str, str] = {}
    expressions: Dict[str, str] = {}

    for dependency in extract_lateral_view_dependencies(select_node):
        output_key = dependency.output_column.lower().strip("`")
        source_relation = scope.resolve_relation(dependency.source_table_alias)
        grouped_inputs.setdefault(output_key, []).append(ColumnRef(
            relation_name=source_relation.relation_name,
            column_name=dependency.source_column,
            relation_kind=source_relation.relation_kind,
            table_alias=source_relation.alias,
        ))
        output_names[output_key] = dependency.output_column
        expressions[output_key] = dependency.transform

    for output_key, inputs in grouped_inputs.items():
        schema.add_dependency(ColumnDependency(
            output=ColumnRef(relation_name, output_names[output_key], relation_kind),
            inputs=_dedupe_column_refs(inputs),
            transform_type="lateral_view",
            expression=expressions[output_key],
            confidence="medium",
        ))
        resolved_columns.add(output_key)


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
