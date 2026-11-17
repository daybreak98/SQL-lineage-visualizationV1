"""Occurrence bindings from the primary resolver; no second SQL name resolver."""
from sqlglot import exp

from app.services.subfield import Analysis, combine


class LocalBindingAnalysis(Analysis):
    def __init__(self, sql, dialect, source_schemas):
        super().__init__(sql, dialect, source_schemas)
        self.column_bindings = []
        self.row_dependencies = []
        self.cases = []
        self.case_binding_stack = []

    def consumer_port(self, node, scope):
        current = node
        while current.parent is not None and current.parent is not scope.expression:
            current = current.parent
        items = scope.expression.selects if isinstance(scope.expression, exp.Select) else []
        for slot, item in enumerate(items, 1):
            if item is current:
                return {"statement": self.statement, "scope": self.scope_ids[scope], "slot": slot}
        return None  # WHERE/ON uses retain scope and clause, never borrow a value slot.

    def on_column_binding(self, node, scope, clause, binding):
        operations = []
        parent = node.parent
        while parent is not None and not isinstance(parent, exp.Select):
            if isinstance(parent, (exp.Func, exp.Cast)):
                operations.append({"kind": type(parent).__name__,
                                   "semantics": "UNVERIFIED", **self.evidence(parent)})
            parent = parent.parent
        entry = {"scope": self.scope_ids[scope], "clause": clause, "binding": binding,
                 "consumer": self.consumer_port(node, scope),
                 "operations": operations, **self.evidence(node)}
        if entry not in self.column_bindings:
            self.column_bindings.append(entry)
        if self.case_binding_stack:
            self.case_binding_stack[-1].append({key: entry[key] for key in ('binding', 'expression', 'position')})

    def case_expression(self, node, scope, outputs, role, clause, record):
        values = []

        def part(child, child_role):
            nested_start = len(self.cases)
            bindings = []
            self.case_binding_stack.append(bindings)
            try:
                value = self.expression(child, scope, outputs, child_role, clause, record=record)
            finally:
                self.case_binding_stack.pop()
            values.append(value)
            evidence = self.evidence(child)
            anchor = min((leaf for leaf in child.walk() if 'start' in leaf.meta and 'end' in leaf.meta),
                         key=lambda leaf: leaf.meta['start'], default=None)
            anchor_position = self.evidence(anchor)['position'] if anchor is not None else None
            return {**evidence, 'anchor_position': evidence['position'] or anchor_position,
                    'kind': value.kind, 'inputs': [origin.as_dict() for origin in value.inputs],
                    'bindings': bindings, 'nested_case_ids': [case['id'] for case in self.cases[nested_start:]]}

        operand = part(node.this, 'CONDITION') if node.this is not None else None
        arms = []
        for slot, branch in enumerate(node.args['ifs'], 1):
            arms.append({'slot': slot, 'kind': 'WHEN', 'guard': part(branch.this, 'CONDITION'),
                         'value': part(branch.args['true'], role)})
        default = node.args.get('default')
        arms.append({'slot': len(arms) + 1, 'kind': 'ELSE' if default is not None else 'IMPLICIT_NULL',
                     'guard': None, 'value': part(default, role) if default is not None else {
                         'kind': 'CONSTANT', 'expression': 'NULL', 'position': None, 'anchor_position': None,
                         'bindings': [], 'inputs': [], 'nested_case_ids': []}})
        outer_operations = []
        parent = node.parent
        while parent is not None and parent is not scope.expression:
            if not isinstance(parent, (exp.Alias, exp.Paren)):
                outer_operations.append({'kind': type(parent).__name__, 'semantics': 'UNVERIFIED', **self.evidence(parent)})
            parent = parent.parent
        self.cases.append({'id': len(self.cases) + 1, 'scope': self.scope_ids[scope], 'clause': clause,
                           'consumer': self.consumer_port(node, scope), 'operand': operand, 'arms': arms,
                           'outer_operations': outer_operations, 'value_role': role, **self.evidence(node)})
        return combine(values)

    def expression(self, node, scope, outputs, role, clause, *, record=True):
        if (isinstance(node, exp.Case) and self.macro_context is None and node.args.get('ifs')
                and all(isinstance(branch, exp.If) and branch.args.get('true') is not None
                        and branch.args.get('false') is None for branch in node.args['ifs'])):
            return self.case_expression(node, scope, outputs, role, clause, record)
        if isinstance(node, exp.Count):
            entry = {"scope": self.scope_ids[scope], "kind": "ROWS",
                     "semantics": "UNVERIFIED", "consumer": self.consumer_port(node, scope),
                     "clause": clause, **self.evidence(node)}
            if entry not in self.row_dependencies:
                self.row_dependencies.append(entry)
        return super().expression(node, scope, outputs, role, clause, record=record)


def analyze_local_bindings(sql, dialect="spark", source_schemas=None, *, on_query=None):
    if dialect not in {"spark", "hive"}:
        raise ValueError("dialect must be hive or spark")
    analysis = LocalBindingAnalysis(sql, dialect, source_schemas)
    analysis.on_query = on_query
    facts = analysis.run()
    generators = {item["scope"]: item["id"] for item in facts["generators"]}
    for occurrence in analysis.column_bindings:
        if occurrence["clause"] == "LATERAL" and occurrence["scope"] in generators:
            occurrence["generator_input_of"] = generators[occurrence["scope"]]
    return {"facts": facts, "column_bindings": analysis.column_bindings, "cases": analysis.cases,
            "row_dependencies": analysis.row_dependencies}
