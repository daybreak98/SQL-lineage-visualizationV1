"""C09 expression dependency analyzer.

Extract deterministic metric/expression information from SELECT projections.
No LLM — based on sqlglot AST evidence only.

Integration: call after parse/name-resolve and before graph_builder finalizes.
"""
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable, List, Optional

import sqlglot
from sqlglot import exp


@dataclass
class ExpressionMetric:
    name: str
    entity_id: str
    expression: str
    depends_on: List[str] = field(default_factory=list)
    aggregate_functions: List[str] = field(default_factory=list)
    operators: List[str] = field(default_factory=list)
    function_names: List[str] = field(default_factory=list)
    description: str = ""
    evidence: dict = field(default_factory=dict)
    confidence_level: str = "high"

    def to_dict(self) -> dict:
        return asdict(self)


class ExpressionAnalyzer:
    """Extract expression dependencies from SELECT projections.

    Conservative: direct column projections don't create expression nodes.
    Aggregates, functions, arithmetic, CASE become metrics.
    """

    def __init__(
        self,
        dialect: str = "spark",
        resolve_column: Optional[Callable[[exp.Column], str]] = None,
    ) -> None:
        self.dialect = dialect
        self.resolve_column = resolve_column or self._default_resolve_column

    def analyze_sql(self, sql: str) -> List[ExpressionMetric]:
        parsed = sqlglot.parse_one(sql, read=self.dialect)
        sel = self._find_main_select(parsed)
        if sel is None:
            return []
        return self.analyze_select(sel)

    def analyze_select(self, sel: exp.Select) -> List[ExpressionMetric]:
        metrics: List[ExpressionMetric] = []
        for projection in sel.expressions:
            metric = self.analyze_projection(projection)
            if metric is not None:
                metrics.append(metric)
        return metrics

    def analyze_projection(self, projection: exp.Expression) -> Optional[ExpressionMetric]:
        output_name = projection.alias_or_name
        if not output_name:
            return None

        expr = projection.this if isinstance(projection, exp.Alias) else projection
        expr_sql = self._safe_sql(expr)
        depends_on = self._extract_dependencies(expr)
        agg_funcs = self._extract_aggregates(expr)
        ops = self._extract_operators(expr)
        func_names = self._extract_functions(expr)

        if not self._needs_expression_metric(
            expr=expr, output_name=output_name,
            aggregate_functions=agg_funcs, operators=ops,
            function_names=func_names, depends_on=depends_on,
        ):
            return None

        return ExpressionMetric(
            name=output_name,
            entity_id=f"output_column:{output_name}",
            expression=expr_sql,
            depends_on=depends_on,
            aggregate_functions=agg_funcs,
            operators=ops,
            function_names=func_names,
            description=self._build_deterministic_description(expr_sql),
            evidence={
                "source": "sqlglot_ast",
                "output_name": output_name,
                "projection_sql": self._safe_sql(projection),
            },
            confidence_level="high" if depends_on else "medium",
        )

    def _find_main_select(self, parsed: exp.Expression) -> Optional[exp.Select]:
        if isinstance(parsed, exp.Select):
            return parsed
        found = parsed.find(exp.Select)
        return found if isinstance(found, exp.Select) else None

    def _extract_dependencies(self, expr: exp.Expression) -> List[str]:
        deps: List[str] = []
        seen: set[str] = set()
        for col in expr.find_all(exp.Column):
            # Skip columns inside table identifiers or star expressions
            if isinstance(col.this, exp.Star):
                continue
            resolved = self.resolve_column(col)
            if resolved and resolved not in seen:
                seen.add(resolved)
                deps.append(resolved)
        return deps

    def _extract_aggregates(self, expr: exp.Expression) -> List[str]:
        funcs: set[str] = set()
        for node in expr.walk():
            if isinstance(node, exp.Sum):
                funcs.add("SUM")
            elif isinstance(node, exp.Avg):
                funcs.add("AVG")
            elif isinstance(node, exp.Min):
                funcs.add("MIN")
            elif isinstance(node, exp.Max):
                funcs.add("MAX")
            elif isinstance(node, exp.Count):
                if self._is_distinct_count(node):
                    funcs.add("COUNT_DISTINCT")
                else:
                    funcs.add("COUNT")
        return sorted(funcs)

    def _extract_operators(self, expr: exp.Expression) -> List[str]:
        ops: set[str] = set()
        for node in expr.walk():
            if isinstance(node, exp.Div):
                ops.add("DIV")
            elif isinstance(node, exp.Mul):
                ops.add("MUL")
            elif isinstance(node, exp.Add):
                ops.add("ADD")
            elif isinstance(node, exp.Sub):
                ops.add("SUB")
        return sorted(ops)

    def _extract_functions(self, expr: exp.Expression) -> List[str]:
        names: set[str] = set()
        for node in expr.walk():
            if isinstance(node, exp.Func):
                sql_name = node.sql_name().upper()
                if sql_name:
                    names.add(sql_name)
        aggregate_names = {"SUM", "AVG", "MIN", "MAX", "COUNT"}
        return sorted(name for name in names if name not in aggregate_names)

    def _needs_expression_metric(
        self, expr: exp.Expression, output_name: str,
        aggregate_functions: Iterable[str], operators: Iterable[str],
        function_names: Iterable[str], depends_on: List[str],
    ) -> bool:
        if aggregate_functions or operators or function_names:
            return True
        if isinstance(expr, exp.Case):
            return True
        if len(depends_on) > 1:
            return True
        if isinstance(expr, exp.Column):
            return False
        if not depends_on:
            return False
        return True

    def _is_distinct_count(self, node: exp.Count) -> bool:
        if isinstance(node.this, exp.Distinct):
            return True
        if bool(node.args.get("distinct")):
            return True
        return "DISTINCT" in self._safe_sql(node).upper()

    def _safe_sql(self, expr: exp.Expression) -> str:
        try:
            return expr.sql(dialect=self.dialect)
        except Exception:
            return str(expr)

    def _default_resolve_column(self, col: exp.Column) -> str:
        table = col.table
        name = col.name
        return f"{table}.{name}" if table else name

    def _build_deterministic_description(self, expr_sql: str) -> str:
        return f"由 SQL 表达式 {expr_sql} 计算得到。"


def metrics_to_semantics_report(metrics: List[ExpressionMetric]) -> dict:
    return {"metrics": [metric.to_dict() for metric in metrics]}
