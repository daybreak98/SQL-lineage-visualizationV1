"""W05: deterministic SQLGlot facts, not an engine or a pruning verifier."""

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re

import sqlglot
from sqlglot import exp
from sqlglot.dialects import Dialect
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import Scope, traverse_scope
from sqlglot.tokens import TokenType

from app.services.subfield_parser import parse_with_json_path_positions


@dataclass(frozen=True)
class Origin:
    source: str
    column: str
    tokens: tuple = ()

    def as_dict(self):
        path = "$"
        for kind, value in self.tokens:
            if kind == "key":
                path += "." + value if re.fullmatch(r"[A-Za-z0-9_]+", value) else "[" + json.dumps(
                    value, ensure_ascii=False
                ) + "]"
            elif kind == "index":
                path += f"[{value}]"
            elif kind == "decode":
                path += f"::decode({value})"
            elif kind == "any_element":
                path += "[*]"
            else:
                path += "::json"
        return {"source": self.source, "column": self.column, "path": path,
                "path_tokens": [{"kind": k, "value": v} for k, v in self.tokens]}


@dataclass(frozen=True)
class Value:
    inputs: tuple[Origin, ...] = ()
    slots: frozenset[int] = frozenset()
    # Only passthrough and builtin extraction retain a path-addressable identity.
    kind: str = "DERIVED"
    exact: Origin | None = None
    generator_ports: frozenset[str] = frozenset()


def combine(values, kind="DERIVED"):
    values = tuple(values)
    return Value(tuple(dict.fromkeys(o for v in values for o in v.inputs)),
                 frozenset().union(*(v.slots for v in values)), kind,
                 generator_ports=frozenset().union(*(v.generator_ports for v in values)))


def passthrough(origin):
    return Value((origin,), kind="WHOLE_RAW", exact=origin)


def path_tokens(node):
    if not isinstance(node, exp.JSONPath):
        return None
    parts = node.expressions
    if not parts or not isinstance(parts[0], exp.JSONPathRoot):
        return None
    result = []
    for part in parts[1:]:
        if isinstance(part, exp.JSONPathKey) and isinstance(part.this, str):
            result.append(("key", part.this))
        elif isinstance(part, exp.JSONPathSubscript) and type(part.this) is int and part.this >= 0:
            result.append(("index", part.this))
        else:
            return None
    return tuple(result)


def literal_text_map_key(node):
    """Recognize one fixed Hive text-map lookup, not JSON or a general subscript."""
    call = node.this
    if (type(call) is not exp.StrToMap or type(call.this) is not exp.Column
            or call.this.is_star or len(node.expressions) != 1
            or set(node.args) - {"this", "expressions"}
            or set(call.args) - {"this", "pair_delim", "key_value_delim"}):
        return None
    key = node.expressions[0]
    if type(key) is not exp.Literal or not key.is_string:
        return None
    for name, delimiter in (("pair_delim", "&"), ("key_value_delim", "=")):
        arg = call.args.get(name)
        if type(arg) is not exp.Literal or not arg.is_string or arg.this != delimiter:
            return None
    return key.this


def only_projection_args(node, allowed):
    # SQLGlot materializes absent arguments as None and some empty lists.
    return all(name in allowed or value is None or value == []
               for name, value in node.args.items())


def finite_case_keys(node):
    """Return syntactic candidate keys, without evaluating guard reachability."""
    if type(node) is not exp.Concat or len(node.expressions) != 2:
        return None
    prefix, case = node.expressions
    if (not isinstance(prefix, exp.Literal) or not prefix.is_string or prefix.this != "$."
            or not isinstance(case, exp.Case) or case.this is not None):
        return None
    arms = case.args.get("ifs") or []
    if not 1 <= len(arms) <= 7 or any(arm.this is None for arm in arms):
        return None
    values = [arm.args.get("true") for arm in arms] + [case.args.get("default")]
    if not all(isinstance(v, exp.Literal) and v.is_string
               and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v.this) for v in values):
        return None
    return tuple(dict.fromkeys(v.this for v in values)), tuple(arm.this for arm in arms)


def binding_declarations(source_schemas):
    """Only complete, evidenced caller declarations can prove column absence."""
    usable = {}
    ignored = {}
    if source_schemas is None:
        return usable, ignored
    if not isinstance(source_schemas, Mapping):
        raise TypeError("source_schemas must be a mapping or None")
    for relation, item in source_schemas.items():
        if not isinstance(relation, str):
            raise TypeError("source_schemas keys must be relation names")
        if not isinstance(item, Mapping) or item.get("complete") is not True:
            ignored[relation] = "INCOMPLETE_DECLARATION"
            continue
        if not all(isinstance(item.get(k), str) and item[k].strip() for k in ("version", "evidence")):
            ignored[relation] = "MISSING_VERSION_OR_EVIDENCE"
            continue
        cols = item.get("columns")
        if not isinstance(cols, list) or not all(
            isinstance(c, str) and c.strip() for c in cols
        ):
            ignored[relation] = "INVALID_COLUMN_LIST"
            continue
        folded = frozenset(c.lower() for c in cols)
        if len(folded) != len(cols):
            ignored[relation] = "AMBIGUOUS_COLUMN_LIST"
            continue
        usable[relation] = (folded, {k: item[k] for k in ("complete", "version", "evidence")})
    return usable, ignored


@dataclass(frozen=True)
class Macro:
    name: str
    parameter: str
    body: exp.Case
    statement: int


def statement_parts(sql, dialect="hive", *, reliable=False):
    """Use dialect tokens, not text splitting. Recovery rejects nested delimiters."""
    tokens = Dialect.get_or_raise(dialect).tokenize(sql)
    if reliable:
        closing = {
            TokenType.L_PAREN: TokenType.R_PAREN,
            TokenType.L_BRACKET: TokenType.R_BRACKET,
            TokenType.L_BRACE: TokenType.R_BRACE,
        }
        stack = []
        for token in tokens:
            kind = token.token_type
            if kind in closing:
                stack.append(closing[kind])
            elif kind in closing.values():
                if not stack or stack.pop() != kind:
                    raise SqlglotError("Unmatched delimiter; statement recovery disabled")
            elif kind == TokenType.SEMICOLON and stack:
                raise SqlglotError("Nested statement delimiter; statement recovery disabled")
            elif (kind not in {TokenType.STRING, TokenType.IDENTIFIER}
                  and token.text.lower() in {"begin", "declare", "delimiter", "procedure"}):
                raise SqlglotError("Possible procedural boundary; statement recovery disabled")
        if stack:
            raise SqlglotError("Unclosed delimiter; statement recovery disabled")
    first = 0
    for i, token in enumerate(tokens):
        if token.token_type == TokenType.SEMICOLON:
            if first < i:
                yield tokens[first:i], token.start, True
            first = i + 1
    if first < len(tokens):
        yield tokens[first:], len(sql), False


def parse_at(sql, start, end, dialect):
    node = sqlglot.parse_one(sql[start:end], read=dialect)
    for child in node.walk():
        if "start" in child.meta and "end" in child.meta:
            meta = child.meta
            meta["start"] += start
            meta["end"] += start
            pos = meta["end"]
            meta["line"] = sql.count("\n", 0, pos) + 1
            meta["col"] = pos - sql.rfind("\n", 0, pos)
    return node


@dataclass(frozen=True)
class StatementFailure:
    position: dict
    message: str


def parse_slice(sql, start, end, dialect, line, cache):
    """Memoize only position-adjusted parse outcomes, before any scope analysis."""
    key = (dialect, start, end)
    if key not in cache:
        try:
            cache[key] = parse_at(sql, start, end, dialect)
        except SqlglotError as err:
            errors = getattr(err, "errors", ())
            description = errors[0]["description"] if errors else type(err).__name__
            cache[key] = StatementFailure({"start": start, "end": end, "line": line}, description)
    return cache[key]


def macro_definition(sql, tokens, end, terminated, index, cache):
    """Recognize only unquoted, single STRING parameter and a closed CASE body."""
    if len(tokens) < 10 or not terminated:
        return None
    name, lparen, parameter, datatype, rparen = tokens[3:8]
    if (not all(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", sql[t.start:t.end + 1])
                for t in (name, parameter))
            or lparen.token_type != TokenType.L_PAREN or rparen.token_type != TokenType.R_PAREN
            or sql[datatype.start:datatype.end + 1].lower() != "string"
            or tokens[8].token_type != TokenType.CASE
            or tokens[-1].token_type != TokenType.END):
        return None
    body_token = tokens[8]
    body = parse_slice(sql, body_token.start, end, "hive", body_token.line, cache)
    if not isinstance(body, exp.Case) or body.this is not None:
        return None
    if any(col.table or col.is_star or col.name.lower() != parameter.text.lower()
           for col in body.find_all(exp.Column)):
        return None
    for sub in body.walk():
        if isinstance(sub, (exp.Query, exp.UDTF, exp.Star, exp.Window, exp.AggFunc)):
            return None
        if isinstance(sub, exp.Anonymous):
            if sub.name.lower() == name.text.lower() or (
                sub.name.lower() != "bigint" and not isinstance(sub.parent, exp.Dot)
            ):
                return None
    return Macro(name.text.lower(), parameter.text.lower(), body, index)


class Analysis:
    def __init__(self, sql, dialect, source_schemas):
        self.sql = sql
        self.dialect = dialect
        self.uses = []
        self.mappings = []
        self.generators = []
        self.windows = []
        self.row_selections = []
        self.locally_reviewable_projection_only = False
        self.allow_text_map_evidence = False
        self.allow_multi_coalesce = False
        self.source_string_tokens = None
        self.unknowns = []
        self.active = set()
        self.statement = 0
        self.macros = {}
        self.seen_macros = set()
        self.macro_context = None
        self.declarations, self.ignored_schemas = binding_declarations(source_schemas)
        self.applied_schemas = {}

    def evidence(self, node):
        # SQLGlot spans often cover the function-name or identifier token only.
        m = node.meta
        if "start" not in m and isinstance(node, exp.Column):
            m = node.this.meta
        position = None
        if "start" in m and "end" in m:
            position = {"start": m["start"], "end": m["end"] + 1,
                        "line": m.get("line"), "column_end": m.get("col")}
        return {"statement": self.statement, "position": position,
                "expression": node.sql(dialect=self.dialect)}

    def map_key_position(self, node):
        """Locate a literal only when AST and original-source tokenizer agree."""
        start, end = node.meta.get("start"), node.meta.get("end")
        if (type(start) is not int or type(end) is not int
                or not 0 <= start <= end < len(self.sql)):
            return None
        if self.source_string_tokens is None:
            try:
                self.source_string_tokens = {
                    (t.start, t.end): t for t in Dialect.get_or_raise(self.dialect).tokenize(self.sql)
                    if t.token_type == TokenType.STRING
                }
            except SqlglotError:
                self.source_string_tokens = {}
        token = self.source_string_tokens.get((start, end))
        if token is None or token.text != node.this:
            return None
        # Token bounds include quotes; API offsets are half-open code points.
        return {"start": start, "end": end + 1, "line": token.line, "column_end": token.col}

    def is_unqualified_builtin(self, node, name):
        meta = node.meta
        return ("start" in meta and "end" in meta and not isinstance(node.parent, exp.Dot)
                and self.sql[meta["start"]:meta["end"] + 1].lower() == name)

    def located_evidence(self, node):
        evidence = self.evidence(node)
        if self.macro_context is not None:
            macro, _, call_evidence = self.macro_context
            evidence["statement"] = macro.statement
            evidence["macro"] = {
                "name": macro.name, "parameter_slot": 1,
                "definition": {"statement": macro.statement, "position": evidence["position"]},
                "call": call_evidence,
            }
        return evidence

    def unknown(self, code, node, clause=None, inputs=()):
        self.unknowns.append({"code": code, "clause": clause,
                              "inputs": [o.as_dict() for o in inputs], **self.located_evidence(node)})

    def use(self, origin, role, clause, kind, node, **extra):
        if clause in {"GROUP_BY", "WINDOW_PARTITION", "WINDOW_ORDER"}:
            extra["scope"] = self.current_scope_id
        self.uses.append({**origin.as_dict(), "role": role, "clause": clause, "kind": kind,
                          **self.located_evidence(node), **extra})

    def expand_macro(self, call, scope, outputs, role, clause, record):
        macro = self.macros[call.name.lower()]
        args = call.expressions
        if len(args) != 1 or not isinstance(args[0], exp.Column):
            children = [self.expression(a, scope, outputs, role, clause, record=record) for a in args]
            value = combine(children, "UNKNOWN")
            self.unknown("UNSUPPORTED_MACRO_ARGUMENT", call, clause, value.inputs)
            return value
        value = self.expression(args[0], scope, outputs, role, clause, record=False)
        if value.exact is None:
            self.unknown("UNBOUND_MACRO_ARGUMENT", call, clause, value.inputs)
            return combine((value,), "UNKNOWN")
        call_evidence = self.evidence(call)
        prev = len(self.unknowns)
        self.macro_context = (macro, value, call_evidence)
        try:
            result = self.expression(macro.body, scope, outputs, role, clause, record=record)
        finally:
            self.macro_context = None
        return combine((result,), "UNKNOWN") if len(self.unknowns) > prev else result

    @staticmethod
    def relations(scope):
        return (dict(scope.lateral_sources) if isinstance(scope.expression, exp.UDTF)
                else {k: v for k, (_, v) in scope.selected_sources.items()})

    def table_may_have_column(self, table, name):
        # Exact SQL relation spelling, no aliases, suffix matches or guessed
        # catalog. Skip multipart names that would collide when joined by dots.
        parts = table.parts
        if (table.alias_column_names or len(parts) < 2
                or any(not isinstance(p, exp.Identifier) or "." in p.name for p in parts)):
            return True
        relation = ".".join(p.name for p in parts)
        declaration = self.declarations.get(relation)
        if declaration is None:
            return True
        columns, provenance = declaration
        self.applied_schemas[relation] = provenance
        return name in columns

    def column_candidates(self, node, scope, outputs):
        sources = self.relations(scope)
        name = node.name.lower()
        if node.table:
            return [alias for alias in sources if alias.lower() == node.table.lower()]
        return [
            alias for alias, src in sources.items()
            if (self.table_may_have_column(src, name) if isinstance(src, exp.Table)
                else name in outputs.get(src, {}) or src in self.open_scopes)
        ]

    def resolve(self, node, scope, outputs, clause):
        name = node.name.lower()
        candidates = self.column_candidates(node, scope, outputs)
        if len(candidates) != 1:
            code = "AMBIGUOUS_COLUMN" if candidates else "UNBOUND_COLUMN"
            self.unknown(code, node, clause)
            return Value(kind="UNKNOWN")
        src = self.relations(scope)[candidates[0]]
        if isinstance(src, exp.Table):
            if src.alias_column_names or not isinstance(src.this, exp.Identifier):
                self.unknown("UNSUPPORTED_SOURCE", node, clause)
                return Value(kind="UNKNOWN")
            if node.db and (node.db.lower(), node.catalog.lower()) != (
                src.db.lower(), src.catalog.lower()
            ):
                self.unknown("UNBOUND_COLUMN", node, clause)
                return Value(kind="UNKNOWN")
            return passthrough(Origin(".".join(p.name for p in src.parts), node.name))
        if node.db or node.catalog:
            self.unknown("UNBOUND_COLUMN", node, clause)
            return Value(kind="UNKNOWN")
        value = outputs.get(src, {}).get(name)
        if value is None:
            self.unknown("UNBOUND_COLUMN", node, clause)
            return Value(kind="UNKNOWN")
        return value

    def same_group_input(self, column, projection, scope, outputs):
        if projection is None:
            return False
        item, value = projection
        direct = item.this if isinstance(item, exp.Alias) else item
        if (not isinstance(direct, exp.Column) or direct.is_star or direct.db or direct.catalog
                or column.name.lower() != direct.name.lower() or value.kind == "UNKNOWN"):
            return False
        bare = self.column_candidates(column, scope, outputs)
        return len(bare) == 1 and bare == self.column_candidates(direct, scope, outputs)

    def expression(self, node, scope, outputs, role, clause, *, record=True):
        def read(child, child_role=role, *, record_child=record):
            return self.expression(child, scope, outputs, child_role, clause, record=record_child)

        if isinstance(node, (exp.Null, exp.Literal, exp.Boolean)):
            return Value(kind="CONSTANT")
        if isinstance(node, (exp.Alias, exp.Paren)):
            return read(node.this)
        if (self.macro_context is None and isinstance(node, exp.Anonymous)
                and not isinstance(node.parent, exp.Dot) and node.name.lower() in self.macros):
            return self.expand_macro(node, scope, outputs, role, clause, record)
        if isinstance(node, exp.Column):
            if node.is_star:
                self.unknown("UNEXPANDED_STAR", node, clause)
                return Value(kind="UNKNOWN")
            val = self.macro_context[1] if self.macro_context is not None else (
                self.resolve(node, scope, outputs, clause)
            )
            if record:
                for o in val.inputs:
                    if role != "VALUE" or val.kind == "WHOLE_RAW":
                        self.use(o, role if role != "VALUE" else "CARRIER", clause,
                                 "BOUND_READ" if o.tokens else "WHOLE_RAW", node)
            return val
        if isinstance(node, (exp.JSONExtractScalar, exp.JSONExtract)):
            base_node = node.this
            while isinstance(base_node, exp.Paren):
                base_node = base_node.this
            body = read(node.this, record_child=record and not isinstance(base_node, exp.Column))
            tokens = path_tokens(node.expression)
            builtin = self.is_unqualified_builtin(node, "get_json_object")
            candidate = None
            if (tokens is None and builtin and self.dialect == "spark" and body.exact is not None
                    and isinstance(node.expression, exp.Concat)
                    and self.is_unqualified_builtin(node.expression, "concat")):
                candidate = finite_case_keys(node.expression)
            if not builtin or (tokens is None and candidate is None):
                self.unknown("UNSUPPORTED_JSON_PATH", node, clause, body.inputs)
                extra = (read(node.expression) if node.expression is not None
                         and not isinstance(node.expression, exp.JSONPath) else Value())
                return combine((body, extra), "UNKNOWN")
            if body.exact is None:
                self.unknown("UNKNOWN_JSON_INPUT", node, clause, body.inputs)
                return combine((body,), "UNKNOWN")
            base = body.exact
            hops = ()
            if body.kind == "ELEMENT_STRING":
                hops = (("decode", "json_string"),)
            elif body.kind == "EXTRACT":
                hops = (("parse", "json"),)
            if candidate is not None:
                keys, predicates = candidate
                origins = [Origin(base.source, base.column, base.tokens + hops + (("key", key),))
                           for key in keys]
                if record:
                    for origin in origins:
                        self.use(origin, role, clause, "EXTRACT_CANDIDATE", node)
                guards = [read(predicate, "CONDITION") for predicate in predicates]
                return combine([Value(tuple(origins), body.slots,
                                      generator_ports=body.generator_ports), *guards],
                               "FINITE_PATH_CANDIDATES")
            origin = Origin(base.source, base.column, base.tokens + hops + tokens)
            if record:
                self.use(origin, role, clause, "EXTRACT", node)
            return Value((origin,), body.slots, "EXTRACT", origin, body.generator_ports)
        if isinstance(node, exp.If):
            branches = [read(node.this, "CONDITION")]
            branches.extend(read(node.args[k]) for k in ("true", "false") if node.args.get(k) is not None)
            return combine(branches)
        if isinstance(node, exp.Case):
            # Simple CASE also controls on the expression before WHEN.
            values = [read(node.this, "CONDITION")] if node.this is not None else []
            values += [read(branch) for branch in node.args.get("ifs", ())]
            if node.args.get("default") is not None:
                values.append(read(node.args["default"]))
            return combine(values)
        if isinstance(node, (exp.Query, exp.Subquery, exp.UDTF, exp.Star)):
            self.unknown("UNSUPPORTED_EXPRESSION", node, clause)
            return Value(kind="UNKNOWN")
        if (isinstance(node, exp.Count) and type(node.this) is exp.Star
                and not any(node.this.args.values()) and not node.expressions):
            # COUNT(*) consumes rows via its enclosing scope, not every value column.
            return Value()
        if isinstance(node, (exp.Explode, exp.ExplodeOuter, exp.Inline, exp.GenerateSeries)):
            child_values = [read(child, "STRUCTURE") for child in node.iter_expressions()]
            value = combine(child_values, "UNKNOWN")
            self.unknown("UNSUPPORTED_GENERATOR", node, clause, value.inputs)
            return value
        if (type(node) is exp.RegexpExtract
                and self.is_unqualified_builtin(node, "regexp_extract")
                and node.this is not None and node.expression is not None):
            subject = read(node.this)
            if record and subject.exact is not None:
                kind = "WHOLE_RAW" if subject.kind == "WHOLE_RAW" else "BOUND_READ"
                self.use(subject.exact, "REPRESENTATION", clause, kind, node,
                         scope=self.current_scope_id, argument_slot=1)
            return combine([subject, *(read(child) for child in node.iter_expressions()
                                        if child is not node.this)])
        if self.allow_text_map_evidence and type(node) is exp.Bracket:
            map_key = literal_text_map_key(node)
            if map_key is not None and self.is_unqualified_builtin(node.this, "str_to_map"):
                call = node.this
                subject = read(call.this)
                if (record and subject.kind == "WHOLE_RAW" and subject.exact is not None
                        and not subject.exact.tokens):
                    self.use(subject.exact, "REPRESENTATION", clause, "WHOLE_RAW", call,
                             scope=self.current_scope_id, argument_slot=1, map_key=map_key,
                             map_key_position=self.map_key_position(node.expressions[0]),
                             function_binding="UNVERIFIED")
                # Keep the old unresolved semantics and the original operand
                # use (including CONDITION in WHERE). All other args are literals.
                self.unknown("UNSUPPORTED_EXPRESSION", node, clause, subject.inputs)
                return combine((subject,), "UNKNOWN")
        child_values = [read(child) for child in node.iter_expressions()]
        merged = combine(child_values)
        if isinstance(node, (exp.Anonymous, exp.FromJson, exp.Window, exp.Bracket, exp.Dot)):
            code = "UNKNOWN_FUNCTION" if isinstance(node, exp.Anonymous) else "UNSUPPORTED_EXPRESSION"
            self.unknown(code, node, clause, merged.inputs)
            return combine(child_values, "UNKNOWN")
        return merged

    def explode(self, scope, outputs, scope_ids):
        node = scope.expression
        gen = node.this
        names = node.alias_column_names
        if not node.alias or len(names) != 1 or gen.this is None or gen.expressions:
            self.unknown("UNSUPPORTED_GENERATOR", node, "LATERAL")
            if gen.this is not None:
                self.expression(gen.this, scope, outputs, "STRUCTURE", "LATERAL")
            return {}
        arg = gen.this
        while isinstance(arg, exp.Paren):
            arg = arg.this
        schema = arg.expression if isinstance(arg, exp.FromJson) else None
        narrow_builtin = (
            self.dialect == "spark" and isinstance(schema, exp.Literal) and schema.is_string
            and re.fullmatch(r"array\s*<\s*string\s*>", schema.this.strip(), re.IGNORECASE)
            and arg.args.get("options") is None
        )
        base = self.expression(arg.this if narrow_builtin else arg,
                               scope, outputs, "STRUCTURE", "LATERAL")
        self.active.update(base.slots)
        generator_id = f"{scope_ids[scope]}:explode"
        port_id = f"{generator_id}:1"
        port = {"id": port_id, "relation_alias": node.alias, "column": names[0], "slot": 1}
        known = narrow_builtin and base.exact is not None
        self.generators.append({
            "id": generator_id, "scope": scope_ids[scope], "consumer_scope": scope_ids.get(scope.parent),
            "function": "explode", "mode": "OUTER" if node.args.get("outer") else "INNER",
            "row_effect": "EXPANSION", "input_semantics": "BUILTIN_ARRAY_STRING" if known else "UNKNOWN",
            "structure_inputs": [o.as_dict() for o in base.inputs], "outputs": [port],
            **self.evidence(gen),
        })
        if known:
            origin = base.exact
            element = Origin(origin.source, origin.column, origin.tokens + (
                ("decode", "array<string>"), ("any_element", None),
            ))
            value = Value((element,), base.slots, "ELEMENT_STRING", element)
        else:
            self.unknown("UNKNOWN_EXPLODE_INPUT_SEMANTICS", arg, "LATERAL", base.inputs)
            value = Value(base.inputs, base.slots, "UNKNOWN")
        return {names[0].lower(): Value(value.inputs, value.slots, value.kind, value.exact,
                                        base.generator_ports | {port_id})}

    def lateral(self, scope, outputs, scope_ids):
        node = scope.expression
        gen = node.this
        if isinstance(node, exp.Lateral) and type(gen) is exp.Explode:
            return self.explode(scope, outputs, scope_ids)
        if (not isinstance(node, exp.Lateral) or not isinstance(gen, exp.Anonymous)
                or gen.name.lower() != "json_tuple"):
            self.unknown("UNSUPPORTED_GENERATOR", node, "LATERAL")
            if gen is not None:
                self.expression(gen, scope, outputs, "STRUCTURE", "LATERAL")
            return {}
        args = gen.expressions
        names = node.alias_column_names
        if args:
            base_node = args[0]
            while isinstance(base_node, exp.Paren):
                base_node = base_node.this
            base = self.expression(args[0], scope, outputs, "STRUCTURE", "LATERAL",
                                   record=not isinstance(base_node, exp.Column))
        else:
            base = Value()
        exact = base.exact
        if (exact is None or len(args) < 2 or len(args) != len(names) + 1
                or len(set(n.lower() for n in names)) != len(names)
                or not all(isinstance(k, exp.Literal) and k.is_string for k in args[1:])):
            self.unknown("UNSUPPORTED_TUPLE_BINDING", gen, "LATERAL", base.inputs)
            return {}
        result = {}
        hops = (("decode", "json_string"),) if base.kind == "ELEMENT_STRING" else (
            (("parse", "json"),) if base.kind == "EXTRACT" else ()
        )
        for slot, (key, alias) in enumerate(zip(args[1:], names), 1):
            origin = Origin(exact.source, exact.column, exact.tokens + hops + (("key", key.this),))
            request_id = len(self.uses)
            self.use(origin, "VALUE", "LATERAL", "TUPLE_REQUEST", gen, slot=slot, alias=alias,
                     key_position=self.evidence(key)["position"])
            result[alias.lower()] = Value((origin,), base.slots | {request_id}, "EXTRACT", origin,
                                          base.generator_ports)
        return result

    def row_number_projection(self, item, scope, outputs, port):
        window = item.this if isinstance(item, exp.Alias) else None
        if (not isinstance(window, exp.Window) or type(window.this) is not exp.RowNumber
                or not self.is_unqualified_builtin(window.this, "row_number")
                or window.args.get("alias") or window.args.get("spec")
                or window.args.get("over") != "OVER"):
            return None
        partition = window.args.get("partition_by") or []
        order = window.args.get("order")
        if not partition or not isinstance(order, exp.Order) or not order.expressions:
            return None
        if any(not isinstance(sort, exp.Ordered) for sort in order.expressions):
            return None
        for key in (*partition, *(sort.this for sort in order.expressions)):
            if not (isinstance(key, exp.Column) and not key.is_star
                    or (type(key) in {exp.JSONExtract, exp.JSONExtractScalar}
                        and isinstance(key.this, exp.Column) and path_tokens(key.expression) is not None
                        and self.is_unqualified_builtin(key, "get_json_object"))):
                return None
        dependencies = []
        window_keys = []
        before = len(self.unknowns)
        for clause, expressions in (("WINDOW_PARTITION", partition), ("WINDOW_ORDER", order.expressions)):
            for key in expressions:
                operand = key.this if isinstance(key, exp.Ordered) else key
                value = self.expression(operand, scope, outputs, "RELATIONAL", clause)
                dependencies.append(value)
                window_keys.append({
                    "clause": clause, "inputs": [origin.as_dict() for origin in value.inputs],
                    "descending": bool(key.args.get("desc")) if isinstance(key, exp.Ordered) else None,
                    "binding_unknown": value.kind == "UNKNOWN",
                    "generator_ports": sorted(value.generator_ports), **self.evidence(operand),
                })
        unresolved = len(self.unknowns) != before or any(v.kind == "UNKNOWN" for v in dependencies)
        self.windows.append({
            "kind": "ROW_NUMBER", "port": port, "keys": window_keys,
            "binding_unknown": unresolved, "tie_break_verified": False, **self.evidence(window.this),
        })
        return combine(dependencies, "UNKNOWN" if unresolved else "DERIVED")

    def rank_filter(self, where, scope, outputs, scope_id):
        predicate = where.this
        if type(predicate) is not exp.EQ:
            return
        column, one = predicate.this, predicate.expression
        if isinstance(one, exp.Column):
            column, one = one, column
        if (not isinstance(column, exp.Column) or column.is_star or column.db or column.catalog
                or not isinstance(one, exp.Literal) or one.is_string or one.this != "1"):
            return
        candidates = self.column_candidates(column, scope, outputs)
        if len(candidates) != 1:
            return
        producer = self.relations(scope)[candidates[0]]
        if not isinstance(producer, Scope) or producer in self.open_scopes:
            return
        port = self.rank_slots.get(producer, {}).get(column.name.lower())
        if port is not None:
            self.row_selections.append({
                "kind": "ROW_NUMBER_EQ_ONE", "role": "RELATIONAL", "clause": "WHERE",
                "scope": scope_id, "producer": port, **self.evidence(column),
                "predicate": predicate.sql(dialect=self.dialect),
            })

    def select(self, scope, outputs, scope_id, root, target):
        node = scope.expression
        slots = {}
        projections = {}
        ranks = {}
        aliases = scope.outer_columns
        if aliases and len(aliases) != len(node.selects):
            self.unknown("UNSUPPORTED_OUTPUT_BINDING", node)
            self.open_scopes.add(scope)
            return {}
        visible_names = aliases or [item.alias_or_name for item in node.selects]
        duplicate_names = set()
        seen_names = set()
        for visible in visible_names:
            folded_name = visible.lower()
            if folded_name in seen_names:
                duplicate_names.add(folded_name)
            seen_names.add(folded_name)
        for index, item in enumerate(node.selects):
            port = {"statement": self.statement, "scope": scope_id, "slot": index + 1}
            rank = self.row_number_projection(item, scope, outputs, port)
            value = rank if rank is not None else self.expression(item, scope, outputs, "VALUE", "SELECT")
            name = aliases[index] if aliases else item.alias_or_name
            if not name or item.is_star:
                if item.is_star:
                    self.open_scopes.add(scope)
                continue
            folded = name.lower()
            if folded in slots:
                self.unknown("AMBIGUOUS_OUTPUT", item, "SELECT")
                slots[folded] = Value(kind="UNKNOWN")
                projections[folded] = None
                ranks.pop(folded, None)
            else:
                slots[folded] = value
                projections[folded] = (item, value)
                if rank is not None:
                    ranks[folded] = port
            port_reads = []
            if root or (scope.is_cte and (
                value.kind == "WHOLE_RAW" or (self.coalesce_branch_evidence and value.kind == "EXTRACT")
            )):
                port_read = self.cte_port_read(item, scope, outputs, value)
                if port_read is not None:
                    port_reads.append(port_read)
            port_model = None
            argument_count = None
            coalesce_args = self.coalesce_args(item) if root else None
            if coalesce_args is not None:
                count = len(coalesce_args)
                port_model = "COALESCE_2" if count == 2 else "COALESCE_N"
                argument_count = count if count > 2 else None
                port_reads = self.coalesce_port_reads(coalesce_args, scope, outputs) if count <= 8 else []
            terminal_binding = (self.terminal_column_binding(item, scope, outputs, value)
                                if folded not in duplicate_names else None)
            self.mapping(scope_id, root, target, index + 1, name, item, value,
                         port_reads, terminal_binding, port_model, argument_count)
            if root:
                self.active.update(value.slots)
        for key, clause, role in (
            ("where", "WHERE", "CONDITION"), ("group", "GROUP_BY", "RELATIONAL"),
            ("having", "HAVING", "RELATIONAL"), ("order", "ORDER_BY", "RELATIONAL"),
            ("qualify", "QUALIFY", "RELATIONAL"),
        ):
            expr = node.args.get(key)
            if expr is None:
                continue
            if (key in {"group", "order", "having", "qualify"}
                    and any(not c.table and c.name.lower() in slots
                            and (key != "group" or not self.same_group_input(
                                c, projections[c.name.lower()], scope, outputs))
                            for c in expr.find_all(exp.Column))):
                self.unknown("POSSIBLE_OUTPUT_ALIAS", expr, clause)
                continue
            if key in {"group", "order"} and any(
                isinstance(x.this if isinstance(x, exp.Ordered) else x, exp.Literal)
                for x in expr.expressions
            ):
                self.unknown("POSITIONAL_CLAUSE", expr, clause)
                continue
            self.active.update(self.expression(expr, scope, outputs, role, clause).slots)
            if key == "where":
                self.rank_filter(expr, scope, outputs, scope_id)
        for join in node.args.get("joins") or []:
            if join.args.get("using") or join.args.get("method") == "NATURAL":
                self.unknown("UNSUPPORTED_JOIN_BINDING", join, "JOIN")
            if join.args.get("on") is not None:
                self.active.update(self.expression(join.args["on"], scope, outputs,
                                                   "RELATIONAL", "JOIN").slots)
        if node.args.get("distinct") is not None:
            self.active.update(combine(slots.values()).slots)
        for key in ("connect", "match", "distribute", "sort", "cluster"):
            if node.args.get(key) is not None:
                self.unknown("UNSUPPORTED_RELATIONAL_CLAUSE", node.args[key], key.upper())
        self.rank_slots[scope] = ranks
        return slots

    def cte_port_read(self, item, scope, outputs, value):
        # This evidence is adjacent to the real binding. Never reconstruct it
        # from equal origins in mappings.inputs (distinct slots can share one).
        if value.exact is None or value.kind not in {"WHOLE_RAW", "EXTRACT"}:
            return None
        node = item.this if isinstance(item, exp.Alias) else item
        while isinstance(node, exp.Paren):
            node = node.this
        tokens = ()
        kind = "PASSTHROUGH"
        json_path_position = None
        if type(node) in {exp.JSONExtractScalar, exp.JSONExtract}:
            if not self.is_unqualified_builtin(node, "get_json_object"):
                return None
            tokens = path_tokens(node.expression)
            if tokens is None:
                return None
            kind = "EXTRACT"
            json_path_position = node.expression.meta.get("json_path_position")
            node = node.this
            while isinstance(node, exp.Paren):
                node = node.this
        read = self.bound_cte_read(node, scope, outputs, kind, tokens)
        if read is not None and json_path_position is not None:
            read["json_path_position"] = dict(json_path_position)
        return read

    def coalesce_args(self, item):
        node = item.this if isinstance(item, exp.Alias) else item
        while isinstance(node, exp.Paren):
            node = node.this
        if (type(node) is not exp.Coalesce or not self.is_unqualified_builtin(node, "coalesce")
                or not only_projection_args(node, {"this", "expressions"})):
            return None
        args = (node.this, *node.expressions)
        if (len(args) < 2 or (len(args) > 2 and not self.allow_multi_coalesce)
                or any(not isinstance(arg, exp.Column) or arg.is_star for arg in args)):
            return None
        return args

    def coalesce_port_reads(self, args, scope, outputs):
        reads = []
        for slot, arg in enumerate(args, 1):
            read = self.bound_cte_read(arg, scope, outputs, "COALESCE_INPUT", ())
            if read is not None:
                reads.append({**read, "argument_slot": slot})
        return reads

    def bound_cte_read(self, node, scope, outputs, kind, tokens):
        if not isinstance(node, exp.Column) or node.is_star or node.db or node.catalog:
            return None
        candidates = self.column_candidates(node, scope, outputs)
        if len(candidates) != 1:
            return None
        producer = self.relations(scope)[candidates[0]]
        if (not isinstance(producer, Scope) or not producer.is_cte
                or producer in self.open_scopes or not isinstance(producer.expression, exp.Select)):
            return None
        producer_scope = self.scope_ids.get(producer)
        slots = self.cte_slots.get(producer, {})
        slot_info = slots.get(node.name.lower())
        position = self.evidence(node)["position"]
        if producer_scope is None or slot_info is None or position is None:
            return None
        slot, producer_kind = slot_info
        if kind != "COALESCE_INPUT" and producer_kind != "WHOLE_RAW":
            return None
        return {"producer": {"statement": self.statement, "scope": producer_scope, "slot": slot},
                "kind": kind, "position": position,
                "path_tokens": [{"kind": token_kind, "value": token_value}
                                for token_kind, token_value in tokens]}

    def terminal_column_binding(self, item, scope, outputs, value):
        if (value.kind != "WHOLE_RAW" or value.exact is None
                or any(projection.is_star for projection in scope.expression.selects)):
            return None
        node = item.this if isinstance(item, exp.Alias) else item
        while isinstance(node, exp.Paren):
            node = node.this
        if not isinstance(node, exp.Column) or node.is_star or self.evidence(node)["position"] is None:
            return None
        candidates = self.column_candidates(node, scope, outputs)
        if len(candidates) != 1:
            return None
        producer = self.relations(scope)[candidates[0]]
        if not isinstance(producer, exp.Table) or not isinstance(producer.this, exp.Identifier):
            return None
        # A SQL relation token is an observed endpoint, not a catalog binding.
        return "SQL_NAMED_RELATION_COLUMN"

    def mapping(self, scope_id, root, target, slot, name, node, value, port_reads=None,
                terminal_binding=None, port_model=None, argument_count=None):
        self.mappings.append({"scope": scope_id, "root": root, "target": target, "slot": slot,
                              "output": name, "kind": value.kind,
                              **({"port_reads": port_reads} if port_reads or port_model else {}),
                              **({"port_model": port_model} if port_model else {}),
                              **({"argument_count": argument_count} if argument_count is not None else {}),
                              **({"terminal_binding": terminal_binding} if terminal_binding else {}),
                              "generator_ports": sorted(value.generator_ports),
                              "inputs": [x.as_dict() for x in value.inputs], **self.evidence(node)})

    def positional_union_inputs(self, scope, outputs):
        node = scope.expression
        if (not isinstance(node, exp.Union) or node.args.get("distinct") is not False
                or scope.outer_columns
                or any(v for k, v in node.args.items() if k not in {"this", "expression", "distinct"})):
            return None
        branches = scope.set_operation_scopes
        if len(branches) != 2:
            return None
        bound = []
        for branch in branches:
            if (not isinstance(branch.expression, exp.Select) or branch in self.open_scopes
                    or branch.outer_columns):
                return None
            items = branch.expression.selects
            names = [item.alias_or_name.lower() for item in items]
            values = outputs.get(branch, {})
            if (not names or any(not name or item.is_star for name, item in zip(names, items))
                    or len(set(names)) != len(names) or any(name not in values for name in names)):
                return None
            bound.append([(name, values[name]) for name in names])
        left, right = bound
        if len(left) != len(right):
            return None
        merged = {}
        supported = {"WHOLE_RAW", "EXTRACT", "ELEMENT_STRING", "CONSTANT"}
        for (name, a), (_, b) in zip(left, right):
            # Do not combine unresolved slots or arbitrary computations that
            # may have only partial dependencies.
            # Even when both are known, do not preserve either exact identity:
            # set-level type coercion and branch selection are not modeled here.
            merged[name] = (combine((a, b)) if a.kind in supported and b.kind in supported
                            else Value(kind="UNKNOWN"))
        self.unknown("UNION_ALL_TYPE_COERCION_UNVERIFIED", node)
        return merged

    def parse_slices(self, *, hive_macros=False, reliable=False, cache=None):
        if cache is None:
            cache = {}
        statements = []
        for idx, (tokens, end, terminated) in enumerate(
            statement_parts(self.sql, self.dialect, reliable=reliable), 1
        ):
            start = tokens[0].start
            if hive_macros:
                prefix = [self.sql[t.start:t.end + 1].lower() for t in tokens[:3]]
                if prefix == ["create", "temporary", "macro"]:
                    macro = macro_definition(self.sql, tokens, end, terminated, idx, cache)
                    statements.append((idx, macro, tokens))
                    continue
            node = parse_slice(self.sql, start, end, self.dialect, tokens[0].line, cache)
            statements.append((idx, node, None))
        return statements

    def run(self):
        parsed = False
        recovered = 0
        statements = []
        try:
            if self.dialect == "hive" and re.search(r"\bmacro\b", self.sql, re.IGNORECASE):
                cache = {}
                slices = self.parse_slices(hive_macros=True, cache=cache)
                parsed = not any(isinstance(node, StatementFailure) for _, node, _ in slices)
                statements = slices if parsed else self.parse_slices(
                    hive_macros=True, reliable=True, cache=cache
                )
            else:
                try:
                    statements = [(i, s, None)
                                  for i, s in enumerate(parse_with_json_path_positions(self.sql, self.dialect), 1)
                                  if s is not None]
                    parsed = True
                except SqlglotError:
                    statements = self.parse_slices(reliable=True)
            if not parsed:
                recovered = sum(node is not None and not isinstance(node, StatementFailure)
                                for _, node, _ in statements)
        except SqlglotError as err:
            self.unknowns.append({"code": "PARSE_ERROR", "statement": None, "position": None,
                                  "message": str(err)})
            statements = []
        # New N-ary evidence does not cross registration/declaration statements.
        # Keep the existing binary contract unchanged.
        if parsed and len(statements) == 1:
            _, only_statement, declaration = statements[0]
            self.allow_multi_coalesce = (
                declaration is None and isinstance(only_statement, exp.Query)
                and not any(w.args.get("udfs") for w in only_statement.find_all(exp.With))
            )
        # A script prefix can change function registration. Do not infer a
        # builtin across any other statement or an inline UDF declaration.
        if parsed and self.dialect == "hive" and len(statements) == 1:
            _, only_statement, declaration = statements[0]
            if declaration is None and isinstance(only_statement, (exp.Query, exp.Insert)):
                self.allow_text_map_evidence = not any(
                    w.args.get("udfs") for w in only_statement.find_all(exp.With)
                )
        for index, statement, declaration_tokens in statements:
            self.statement = index
            if isinstance(statement, StatementFailure):
                self.unknowns.append({"code": "PARSE_ERROR", "statement": index,
                                      "position": statement.position, "message": statement.message})
                self.macros.clear()
                continue
            if declaration_tokens is not None:
                token = declaration_tokens[3] if len(declaration_tokens) > 3 else declaration_tokens[0]
                name = token.text.lower()
                duplicate = name in self.seen_macros
                self.seen_macros.add(name)
                if duplicate or statement is None:
                    self.macros.pop(name, None)
                    self.unknowns.append({
                        "code": "MACRO_REDEFINITION" if duplicate else "UNSUPPORTED_MACRO_DEFINITION",
                        "statement": index, "clause": None, "inputs": [], "expression": token.text,
                        "position": {"start": token.start, "end": token.end + 1,
                                     "line": token.line, "column_end": token.col},
                    })
                else:
                    self.macros[name] = statement
                continue
            query = statement
            target = None
            if isinstance(statement, (exp.Insert, exp.Create)):
                target = statement.this.sql(dialect=self.dialect)
                query = statement.args.get("expression")
            if not isinstance(query, exp.Query):
                self.unknown("UNSUPPORTED_STATEMENT", statement)
                self.macros.clear()  # may alter the visible session environment
                continue
            if query.args.get("with_") and query.args["with_"].args.get("recursive"):
                self.unknown("RECURSIVE_QUERY", query)
                continue
            try:
                self.query(query, target, check_projection=(
                    parsed and self.dialect == "spark" and len(statements) == 1
                    and type(statement) is exp.Select
                ))
            except SqlglotError as err:
                self.unknown("SCOPE_ERROR", query)
                self.unknowns[-1]["message"] = str(err)
        if sum(tokens is None for _, _, tokens in statements) > 1:
            self.unknowns.append({"code": "CROSS_STATEMENT_BINDING_UNVERIFIED",
                                  "statement": None, "position": None})
        gaps = {u["statement"] for u in self.unknowns}
        for i, use in enumerate(self.uses):
            if use["kind"] == "TUPLE_REQUEST":
                use["active"] = True if i in self.active else (
                    None if None in gaps or use["statement"] in gaps else False
                )
        return {
            "uses": self.uses, "mappings": self.mappings, "unknowns": self.unknowns,
            "generators": self.generators,
            "windows": self.windows, "row_selections": self.row_selections,
            "coverage": {"parsed": parsed, "partial": not parsed and recovered > 0,
                         "recovered": recovered, "complete": False,
                         "locally_reviewable_projection_only": self.locally_reviewable_projection_only,
                         "fragment_supported": parsed and bool(self.mappings) and not self.unknowns,
                         "source_boundary": "SQL_NAMED_RELATIONS",
                         "catalog_verified": False, "engine_semantics_verified": False,
                         "source_schema_binding": {
                             "basis": "CALLER_DECLARATION",
                             "applied": self.applied_schemas,
                             "ignored": self.ignored_schemas,
                             "not_applied": sorted(self.declarations.keys() - self.applied_schemas.keys()),
                         },
                         "dialect": self.dialect, "sqlglot": sqlglot.__version__,
                         "sql_sha256": hashlib.sha256(self.sql.encode("utf-8")).hexdigest()},
        }

    def projection_only(self, query, scopes):
        def identifier(node):
            return (type(node) is exp.Identifier and bool(node.name)
                    and only_projection_args(node, {"this", "quoted"}))

        def relation_alias(node):
            return (type(node) is exp.TableAlias and identifier(node.this)
                    and only_projection_args(node, {"this", "columns"})
                    and all(identifier(c) for c in node.columns))

        def qualifiers(node, parts):
            return all(node.args.get(k) is None or identifier(node.args[k]) for k in parts)

        def column(node):
            return (type(node) is exp.Column and identifier(node.this)
                    and qualifiers(node, ("table", "db", "catalog"))
                    and only_projection_args(node, {"this", "table", "db", "catalog"}))

        def projection(node):
            if type(node) is exp.Alias:
                if (not identifier(node.args.get("alias"))
                        or not only_projection_args(node, {"this", "alias"})):
                    return False
                node = node.this
            if column(node):
                return True
            if (type(node) not in {exp.JSONExtractScalar, exp.JSONExtract}
                    or not column(node.this) or not self.is_unqualified_builtin(node, "get_json_object")
                    or not only_projection_args(node, {"this", "expression"})):
                return False
            path = node.expression
            return (path_tokens(path) is not None and only_projection_args(path, {"expressions"})
                    and all(only_projection_args(part, {"this"} if i else set())
                            for i, part in enumerate(path.expressions)))

        if not scopes or scopes[-1].expression is not query:
            return False
        scoped = {id(scope.expression) for scope in scopes}
        for scope in scopes:
            select = scope.expression
            if (type(select) is not exp.Select
                    or not only_projection_args(select, {"expressions", "from_", "with_"})
                    or not select.expressions or not all(projection(e) for e in select.expressions)):
                return False
            with_clause = select.args.get("with_")
            if with_clause is not None and (
                type(with_clause) is not exp.With or not with_clause.expressions
                or not only_projection_args(with_clause, {"expressions"})
                or not all(type(cte) is exp.CTE and type(cte.this) is exp.Select
                           and id(cte.this) in scoped and relation_alias(cte.args.get("alias"))
                           and only_projection_args(cte, {"this", "alias"})
                           for cte in with_clause.expressions)
            ):
                return False
            from_clause = select.args.get("from_")
            if (type(from_clause) is not exp.From or not only_projection_args(from_clause, {"this"})
                    or len(scope.selected_sources) != 1):
                return False
            source = from_clause.this
            if type(source) is exp.Table:
                alias = source.args.get("alias")
                if (not identifier(source.this) or not qualifiers(source, ("db", "catalog"))
                        or (alias is not None and not relation_alias(alias))
                        or not only_projection_args(source, {"this", "db", "catalog", "alias"})):
                    return False
            elif (type(source) is not exp.Subquery or type(source.this) is not exp.Select
                  or id(source.this) not in scoped or not relation_alias(source.args.get("alias"))
                  or not only_projection_args(source, {"this", "alias"})):
                return False
        return True

    def query(self, query, target, *, check_projection=False):
        scopes = traverse_scope(query)
        outputs = {}
        self.open_scopes = set()
        if not scopes:
            self.unknown("NO_QUERY_SCOPE", query)
        scope_ids = {scope: f"{self.statement}:{idx}" for idx, scope in enumerate(scopes, 1)}
        self.scope_ids = scope_ids
        self.cte_slots = {}
        self.rank_slots = {}
        self.coalesce_branch_evidence = type(query) is exp.Select and any(
            self.coalesce_args(item) is not None for item in query.selects
        )
        # Branches have native scopes. Report branch facts without pretending
        # that set-level output coercion or a production target was analyzed.
        plain_union = (
            self.dialect == "hive" and target is None and isinstance(query, exp.Union)
            and query.args.get("distinct") is False
            and isinstance(query.this, exp.Select) and isinstance(query.expression, exp.Select)
            and not any(v for k, v in query.args.items() if k not in {"this", "expression", "distinct"})
        )
        for scope, scope_id in scope_ids.items():
            self.current_scope_id = scope_id
            source = scope.expression
            root = source is query
            if isinstance(source, exp.Select):
                outputs[scope] = self.select(scope, outputs, scope_id, root, target if root else None)
                if scope.is_cte and scope not in self.open_scopes:
                    names = scope.outer_columns or [item.alias_or_name for item in source.selects]
                    self.cte_slots[scope] = {
                        name.lower(): (idx, outputs[scope][name.lower()].kind)
                        for idx, (name, item) in enumerate(zip(names, source.selects), 1)
                        if (name and not item.is_star
                            and outputs[scope].get(name.lower(), Value()).kind in {"WHOLE_RAW", "EXTRACT"})
                    }
            elif isinstance(source, exp.UDTF):
                outputs[scope] = self.lateral(scope, outputs, scope_ids)
                if not outputs[scope]:
                    self.open_scopes.add(scope)
                for slot, alias in enumerate(source.alias_column_names, 1):
                    if alias.lower() in outputs[scope]:
                        self.mapping(scope_id, False, None, slot, alias, source,
                                     outputs[scope][alias.lower()])
            else:
                merged = self.positional_union_inputs(scope, outputs) if not root else None
                if merged is not None:
                    outputs[scope] = merged
                    continue
                self.unknown("UNION_ALL_BRANCHES_ONLY" if root and plain_union and self.macros
                             else "UNSUPPORTED_SCOPE", source)
                self.open_scopes.add(scope)
        if check_projection:
            self.locally_reviewable_projection_only = self.projection_only(query, scopes)


def analyze_subfields(sql: str, dialect: str = "spark", source_schemas: Mapping | None = None) -> dict:
    """Return local facts; optional caller declarations narrow bare-column binding only."""
    if dialect not in {"spark", "hive"}:
        raise ValueError("dialect must be 'spark' or 'hive'")
    return Analysis(sql, dialect, source_schemas).run()
