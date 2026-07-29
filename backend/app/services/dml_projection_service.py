from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp

from app.models import OutputField


@dataclass(frozen=True)
class DmlProjectionResult:
    tree: exp.Select
    output_fields: list[OutputField]


def build_dml_projection(
    tree: exp.Expression | None,
    dialect: str = "spark",
) -> DmlProjectionResult | None:
    """Convert supported DML writes into a source-only lineage projection."""
    if isinstance(tree, exp.Insert):
        return _build_insert_projection(tree, dialect)
    if isinstance(tree, exp.Merge):
        return _build_merge_projection(tree, dialect)
    return None


def _build_insert_projection(
    tree: exp.Insert,
    dialect: str,
) -> DmlProjectionResult | None:
    source_query = tree.expression
    if not isinstance(source_query, exp.Select):
        return None

    target_columns = _insert_target_columns(tree)
    projections = list(source_query.expressions)
    if target_columns:
        if len(target_columns) != len(projections):
            return None
        projections = [
            projection.copy().as_(target_name, quoted=False)
            for projection, target_name in zip(projections, target_columns)
        ]

    analysis_tree = source_query.copy()
    analysis_tree.set("expressions", projections)
    return DmlProjectionResult(
        tree=analysis_tree,
        output_fields=_output_fields(projections, dialect),
    )


def _build_merge_projection(
    tree: exp.Merge,
    dialect: str,
) -> DmlProjectionResult | None:
    source = tree.args.get("using")
    whens = tree.args.get("whens")
    if not isinstance(source, exp.Expression) or not isinstance(whens, exp.Whens):
        return None

    mappings: list[tuple[str, exp.Expression]] = []
    seen: set[tuple[str, str]] = set()
    output_names: list[str] = []
    output_name_keys: set[str] = set()
    for when in whens.expressions:
        action = when.args.get("then") if isinstance(when, exp.When) else None
        for target_name, source_expression in _merge_action_mappings(action):
            key = (target_name.lower(), source_expression.sql(dialect=dialect))
            if key in seen:
                continue
            seen.add(key)
            mappings.append((target_name, source_expression))
            if target_name.lower() not in output_name_keys:
                output_names.append(target_name)
                output_name_keys.add(target_name.lower())

    if not mappings:
        return None

    projections = [
        source_expression.copy().as_(target_name, quoted=False)
        for target_name, source_expression in mappings
    ]
    analysis_tree = exp.select(*projections).from_(source.copy())
    first_expression_by_output: dict[str, exp.Expression] = {}
    for target_name, source_expression in mappings:
        first_expression_by_output.setdefault(target_name.lower(), source_expression)
    output_fields = [
        OutputField(
            name=name,
            display_name=name,
            expression=first_expression_by_output[name.lower()].sql(dialect=dialect),
            source_type="expression",
        )
        for name in output_names
    ]
    return DmlProjectionResult(tree=analysis_tree, output_fields=output_fields)


def _insert_target_columns(tree: exp.Insert) -> list[str]:
    target = tree.this
    if not isinstance(target, exp.Schema):
        return []
    return [
        expression.name
        for expression in target.expressions
        if getattr(expression, "name", "")
    ]


def _merge_action_mappings(
    action: exp.Expression | None,
) -> list[tuple[str, exp.Expression]]:
    if isinstance(action, exp.Update):
        result: list[tuple[str, exp.Expression]] = []
        for assignment in action.expressions:
            if not isinstance(assignment, exp.EQ):
                continue
            target_name = getattr(assignment.this, "name", "")
            if target_name and isinstance(assignment.expression, exp.Expression):
                result.append((target_name, assignment.expression))
        return result

    if isinstance(action, exp.Insert):
        targets = getattr(action.this, "expressions", None) or []
        values = getattr(action.expression, "expressions", None) or []
        if len(targets) != len(values):
            return []
        return [
            (target.name, value)
            for target, value in zip(targets, values)
            if getattr(target, "name", "") and isinstance(value, exp.Expression)
        ]

    return []


def _output_fields(
    projections: list[exp.Expression],
    dialect: str,
) -> list[OutputField]:
    return [
        OutputField(
            name=projection.alias_or_name,
            display_name=projection.alias_or_name,
            expression=(
                projection.this.sql(dialect=dialect)
                if isinstance(projection, exp.Alias)
                else projection.sql(dialect=dialect)
            ),
            source_type="expression" if isinstance(projection, exp.Alias) else "unknown",
        )
        for projection in projections
    ]
