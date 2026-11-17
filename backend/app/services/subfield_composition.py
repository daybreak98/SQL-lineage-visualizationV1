"""V2 local structural composition. Static observations never authorize pruning.

The thin adapter uses primary analysis scopes and column occurrences. Cross-snapshot
bindings are explicit caller contracts; flattened mappings.inputs are not edges.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope

from app.services.subfield import path_tokens


def _key(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _position(node):
    meta = node.this.meta if isinstance(node, exp.Column) else node.meta
    if type(meta.get("start")) is int and type(meta.get("end")) is int:
        return {"start": meta["start"], "end": meta["end"] + 1,
                "line": meta.get("line"), "column_end": meta.get("col")}
    return None

def _case_parts(case):
    if case["operand"] is not None:
        yield {"case_id": case["id"], "part": "OPERAND"}, case["operand"]
    for arm in case["arms"]:
        for kind in ("guard", "value"):
            if arm[kind] is not None:
                yield {"case_id": case["id"], "arm_slot": arm["slot"], "part": kind.upper()}, arm[kind]


def build_snapshot(sql, snapshot_id, dialect="hive", source_context=None):
    """Build occurrence edges from an explicit, unchanged SQL input.

    source_context is provenance only: it never supplies binding candidates.
    Templates must be supplied as explicitly scoped excerpts, never guessed here.
    No physical output schema is inferred from a SELECT alias or historical DDL.
    """
    digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    result = {"snapshot_id": snapshot_id, "sql_sha256": digest, "dialect": dialect,
              "sqlglot": sqlglot.__version__, "source_context": deepcopy(source_context),
              "ports": [], "relations": [], "row_relations": [], "unknowns": [], "writes": [], "scopes": [], "cases": []}
    from app.services.subfield_local import analyze_local_bindings
    queries = []
    primary = analyze_local_bindings(sql, dialect, on_query=queries.append)
    bindings = defaultdict(list)
    generator_inputs = defaultdict(list)
    for entry in primary["column_bindings"]:
        bindings[(entry["statement"], entry["scope"], _key(entry["position"]))].append(entry["binding"])
        if "generator_input_of" in entry and entry["position"] is not None:
            generator_inputs[entry["statement"], entry["scope"], entry["generator_input_of"]].append(entry)
    generators = {(g["statement"], g["scope"]): g for g in primary["facts"].get("generators", [])}
    result["binding_provider"] = "PRIMARY_ANALYSIS_RESOLVER"
    result["windows"] = deepcopy(primary["facts"].get("windows", []))
    result["unknowns"].extend({"origin": "PRIMARY_ANALYSIS", **deepcopy(u)}
                              for u in primary["facts"]["unknowns"])
    if not primary["facts"]["coverage"]["parsed"]:
        result["unknowns"].append({"code": "PARSE_ERROR", "scope": None,
                                   "message": "Complete SQL parse required for composition"})
        return result
    # Join primary CASE parts to the existing SELECT occurrences by complete
    # consumer identity, token position and confirmed producer binding.
    cases_by_port = defaultdict(list)
    case_occurrences = defaultdict(list)
    for case in primary.get("cases", []):
        if case["clause"] != "SELECT" or case["consumer"] is None:
            continue
        identity = _key(case["consumer"])
        cases_by_port[identity].append(case)
        for part_key, part in _case_parts(case):
            for occurrence in part["bindings"]:
                if occurrence["position"] is not None:
                    key = (identity, _key(occurrence["position"]), _key(occurrence["binding"]))
                    if part_key not in case_occurrences[key]:
                        case_occurrences[key].append(part_key)
    for context in queries:
        statement, tree, query = (context[k] for k in ("statement", "tree", "query"))
        ids = context["scope_ids"]
        scopes = ids.keys()
        slots = {}
        generator_ports = {}
        for scope in scopes:
            slots[scope] = []
            where = scope.expression.args.get("where")
            result["scopes"].append({"statement": statement, "scope": ids[scope],
                "where_expression": where.sql(dialect=dialect) if where else None,
                "source_relations": [".".join(p.name for p in source.parts)
                                     for _, source in scope.selected_sources.values() if isinstance(source, exp.Table)]})
            generator = generators.get((statement, ids[scope])) if isinstance(scope.expression, exp.UDTF) else None
            if generator is not None and generator["position"] == _position(scope.expression.this):
                for output in generator["outputs"]:
                    port = {"snapshot": snapshot_id, "sql_sha256": digest, "statement": statement,
                            "scope": ids[scope], "slot": output["slot"]}
                    row = {"port": port, "output": output["column"], "root": False,
                           "expression": generator["expression"],
                           "position": output.get("key_position") or generator["position"],
                           "generator_id": generator["id"], "generator_output": deepcopy(output),
                           "observes_rows": False, "constant": False}
                    generator_ports[ids[scope], output["slot"]] = row
                    slots[scope].append(row)
                    result["ports"].append(row)
                continue
            if isinstance(scope.expression, exp.UDTF):
                continue
            identities = context["ports"][scope]
            if isinstance(scope.expression, exp.SetOperation) and not identities:
                # A describes UNION branches individually. Its scope objects and
                # branch slots determine this synthetic positional junction.
                children = scope.set_operation_scopes
                signatures = [tuple(row["port"]["slot"] for row in slots.get(child, ()))
                              for child in children]
                expected = tuple(range(1, len(scope.expression.selects) + 1))
                if children and all(signature == expected for signature in signatures):
                    identities = [{"statement": statement, "scope": ids[scope], "slot": slot}
                                  for slot in signatures[0]]
            for identity in identities:
                slot = identity["slot"]
                item = scope.expression.selects[slot - 1]
                port = {"snapshot": snapshot_id, "sql_sha256": digest, **identity}
                name = (scope.outer_columns[slot - 1] if slot <= len(scope.outer_columns)
                        else item.alias_or_name)
                row = {"port": port, "output": name, "root": scope.expression is query,
                       "expression": item.sql(dialect=dialect), "position": _position(item),
                       "observes_rows": any(item.find_all(exp.Count)),
                       "constant": isinstance(item.this if isinstance(item, exp.Alias) else item,
                                              (exp.Literal, exp.Null, exp.Boolean))}
                cases = cases_by_port[_key(identity)]
                result["cases"].extend({**deepcopy(case), "consumer": port} for case in cases)
                bare_item = item.this if isinstance(item, exp.Alias) else item
                if isinstance(bare_item, exp.Case) and len(cases) == 1 and all(
                        part["kind"] == "CONSTANT" for _, part in _case_parts(cases[0])):
                    row["constant"] = True
                slots[scope].append(row)
                result["ports"].append(row)

        def gap(code, scope, **extra):
            result["unknowns"].append({"code": code, "statement": statement,
                                       "scope": ids[scope], **extra})

        def endpoint_for(binding, scope):
            if binding["kind"] == "PROJECTION":
                producer = binding["producer"]
                if "generator_id" in binding:
                    row = generator_ports.get((producer["scope"], producer["slot"]))
                    if (row is None or row["generator_id"] != binding["generator_id"]
                            or row["generator_output"]["column"] != binding["column"]
                            or row["generator_output"]["relation_alias"] != binding["relation_alias"]):
                        gap("GENERATOR_OUTPUT_BINDING_UNVERIFIED", scope, binding=deepcopy(binding))
                        return {}
                return {"producer": {"snapshot": snapshot_id, "sql_sha256": digest, **producer}}
            if binding["kind"] == "NAMED_SOURCE":
                return {"source": {"snapshot": snapshot_id, "sql_sha256": digest,
                    "statement": statement, "scope": ids[scope],
                    "relation": binding["source"], "column": binding["column"],
                    "binding": "SQL_NAMED_RELATION_COLUMN"}}
            gap("SOURCE_KIND_UNSUPPORTED", scope)
            return {}

        def bind(column, scope):
            # Only the primary resolver can affirm a column occurrence binding.
            # ASTs supply operations/consumer slots, never a second name lookup.
            matched = bindings.get((statement, ids[scope], _key(_position(column))), [])
            unique = {_key(binding): binding for binding in matched}
            if len(unique) != 1 or column.is_star:
                gap("COLUMN_BINDING_UNVERIFIED", scope, expression=column.sql(), position=_position(column))
                return {}
            binding, = unique.values()
            return binding

        def edges(expression, scope, consumer, role, clause):
            for column in expression.find_all(exp.Column):
                # Never assign an inner SELECT occurrence to an outer scope.
                nearest = column.find_ancestor(exp.Select)
                if nearest is not scope.expression:
                    gap("NESTED_EXPRESSION_BOUNDARY", scope, expression=column.sql())
                    continue
                binding = bind(column, scope)
                case_parts = ()
                if clause == "SELECT" and binding:
                    identity = _key({k: consumer[k] for k in ("statement", "scope", "slot")})
                    case_parts = case_occurrences.get((identity, _key(_position(column)), _key(binding)), ())
                is_case_control = False
                operations = []
                current = column
                while current is not expression and current.parent is not None:
                    parent = current.parent
                    # A attributes the binding to its innermost CASE part. Walk the
                    # same SELECT AST to see whether that value feeds an outer guard.
                    if case_parts and current is parent.this and (
                            isinstance(parent, exp.Case) or
                            isinstance(parent, exp.If) and isinstance(parent.parent, exp.Case)
                            and parent.arg_key == "ifs"):
                        is_case_control = True
                        break  # Transforms above this guard operate on the CASE result.
                    if isinstance(parent, (exp.JSONExtract, exp.JSONExtractScalar)) and current is parent.this:
                        tokens = path_tokens(parent.expression)
                        operations.append({"kind": "EXTRACT" if tokens is not None else "OPAQUE_PATH",
                                           "path_tokens": [{"kind": k, "value": v} for k, v in tokens or ()]})
                    elif isinstance(parent, exp.Cast):
                        operations.append({"kind": "CAST", "type": parent.to.sql()})
                    elif isinstance(parent, exp.AggFunc):
                        operations.append({"kind": "AGGREGATE", "name": parent.sql_name(),
                                           "expression": parent.sql(dialect=dialect)})
                    elif isinstance(parent, exp.Window):
                        operations.append({"kind": "WINDOW", "semantics": "UNVERIFIED",
                                           "expression": parent.sql(dialect=dialect), "tie_break_verified": False})
                    elif isinstance(parent, exp.Anonymous) or isinstance(parent, exp.Dot):
                        operations.append({"kind": "OPAQUE_FUNCTION", "expression": parent.sql(dialect=dialect)})
                        gap("UNKNOWN_FUNCTION_SEMANTICS", scope, position=_position(parent), expression=parent.sql())
                    elif isinstance(parent, exp.RegexpExtract):
                        op = {"kind": "TRANSFORM", "name": parent.sql_name()}
                        pattern, group = parent.expression, parent.args.get("group")
                        if (current is parent.this and isinstance(pattern, exp.Literal) and pattern.is_string
                                and isinstance(group, exp.Literal) and group.is_int):
                            pattern_pos, group_pos = _position(pattern), _position(group)
                            function_pos = _position(parent)
                            # Report only explicit original tokens, preserving SQL escaping.
                            if pattern_pos and group_pos and function_pos:
                                op.update(representation="REGEX_WHOLE_INPUT_STRING",
                                          pattern_sql=sql[pattern_pos["start"]:pattern_pos["end"]],
                                          capture_group=int(group.this), function_position=function_pos)
                        operations.append(op)
                    elif clause == "SELECT" and isinstance(parent, exp.Binary) and isinstance(parent, exp.Predicate):
                        operations.append({"kind": "COMPARISON", "name": parent.key.upper()})
                    elif clause == "SELECT" and isinstance(parent, (
                            exp.Add, exp.Sub, exp.Mul, exp.Div, exp.IntDiv, exp.Mod, exp.Pow, exp.Neg)):
                        operations.append({"kind": "ARITHMETIC", "name": parent.key.upper()})
                    elif isinstance(parent, exp.Func) and not isinstance(parent, (exp.Coalesce, exp.Case)):
                        operations.append({"kind": "TRANSFORM", "name": parent.sql_name()})
                    current = parent
                if is_case_control:
                    operations = [op for op in operations if op["kind"] not in {"COMPARISON", "ARITHMETIC"}]
                endpoint = endpoint_for(binding, scope) if binding else {}
                if endpoint:
                    evidence = {"position": _position(column), "expression": expression.sql(dialect=dialect),
                                "origin": "AST_SCOPE_OCCURRENCE"}
                    if case_parts:
                        evidence["case_parts"] = deepcopy(case_parts)
                    result["relations" if role == "VALUE" else "row_relations"].append({
                        "consumer": consumer, **endpoint, "role": "CONDITION" if is_case_control else role,
                        "clause": clause, "operations": operations, "evidence": evidence})

        for scope in scopes:
            node = scope.expression
            if isinstance(node, exp.UDTF) and slots[scope]:
                generator = generators[statement, ids[scope]]
                gap("GENERATOR_SEMANTICS_UNVERIFIED", scope, generator_id=generator["id"],
                    position=generator["position"])
                for entry in generator_inputs[statement, ids[scope], generator["id"]]:
                    endpoint = endpoint_for(entry["binding"], scope)
                    if not endpoint:
                        continue
                    for row in slots[scope]:
                        operation = {"kind": "GENERATOR", "generator_id": generator["id"],
                                     "semantics": "UNVERIFIED", "output": row["generator_output"],
                                     **{name: generator[name] for name in ("function", "mode", "row_effect",
                                         "input_semantics", "expression", "position") if name in generator}}
                        result["relations"].append({"consumer": row["port"], **endpoint,
                            "role": "STRUCTURE", "clause": "GENERATOR_INPUT",
                            "operations": [*deepcopy(entry["operations"]), operation],
                            "evidence": {"origin": "PRIMARY_GENERATOR_INPUT_OCCURRENCE",
                                         "position": entry["position"], "expression": entry["expression"]}})
                continue
            if isinstance(node, exp.SetOperation):
                for child in scope.set_operation_scopes:
                    if (not slots[scope] or [row["port"]["slot"] for row in slots.get(child, ())]
                            != [row["port"]["slot"] for row in slots[scope]]):
                        gap("UNION_ARITY_UNVERIFIED", scope)
                        continue
                    for port, producer in zip(slots[scope], slots[child]):
                        result["relations"].append({"consumer": port["port"], "producer": producer["port"],
                            "role": "VALUE", "clause": "UNION", "operations": [{"kind": "UNION_BRANCH"}],
                            "evidence": {"origin": "AST_POSITIONAL_UNION", "position": None}})
                    result["row_relations"].append({
                        "consumer": {"snapshot": snapshot_id, "sql_sha256": digest, "statement": statement,
                                     "scope": ids[scope], "operator": "ROW_SEMANTICS"},
                        "producer": {"snapshot": snapshot_id, "sql_sha256": digest, "statement": statement,
                                     "scope": ids[child], "operator": "ROW_SEMANTICS"},
                        "role": "ROWSET", "clause": "UNION", "operations": [{"kind": "ROW_SOURCE"}],
                        "evidence": {"origin": "AST_POSITIONAL_UNION", "position": None}})
                continue
            if not isinstance(node, exp.Select):
                gap("SCOPE_UNSUPPORTED", scope)
                continue
            for function in node.find_all(exp.Anonymous):
                if function.find_ancestor(exp.Select) is node and not any(function.find_all(exp.Column)):
                    gap("EXTERNAL_CONFIG_OR_FUNCTION_CONTRACT_REQUIRED", scope,
                        expression=function.sql(dialect=dialect), position=_position(function))
            port_by_slot = {row["port"]["slot"]: row["port"] for row in slots[scope]}
            for slot, item in enumerate(node.selects, 1):
                port = port_by_slot.get(slot)
                if item.is_star or any(c.is_star for c in item.find_all(exp.Column)):
                    gap("STAR_SCHEMA_REQUIRED", scope, port=port)
                if port is not None:
                    edges(item, scope, port, "VALUE", "SELECT")
            row_consumer = {"snapshot": snapshot_id, "sql_sha256": digest, "statement": statement,
                            "scope": ids[scope], "operator": "ROW_SEMANTICS"}
            windows = [w for w in node.find_all(exp.Window) if w.find_ancestor(exp.Select) is node]
            for window in windows:
                gap("WINDOW_SEMANTICS_UNVERIFIED", scope, expression=window.sql(dialect=dialect),
                    tie_break_verified=False)
                edges(window, scope, row_consumer, "ROWSET", "WINDOW")
            # A query observes rows even when COUNT(*) or a literal has no
            # value-column occurrence. This is a row endpoint, not whole values.
            for _, source in scope.selected_sources.values():
                if isinstance(source, exp.Table):
                    endpoint = {"source": {"snapshot": snapshot_id, "sql_sha256": digest,
                        "statement": statement, "scope": ids[scope],
                        "relation": ".".join(p.name for p in source.parts), "column": None,
                        "binding": "SQL_RELATION_ROWS"}}
                elif isinstance(source, Scope) and source in ids:
                    endpoint = {"producer": {"snapshot": snapshot_id, "sql_sha256": digest,
                        "statement": statement, "scope": ids[source], "operator": "ROW_SEMANTICS"}}
                else:
                    gap("ROW_SOURCE_UNVERIFIED", scope)
                    continue
                result["row_relations"].append({"consumer": row_consumer, **endpoint,
                    "role": "ROWSET", "clause": "FROM", "operations": [{"kind": "ROW_SOURCE"}],
                    "evidence": {"origin": "AST_SCOPE_FROM", "position": _position(source) if isinstance(source, exp.Table) else None}})
            for clause in ("where", "group", "having", "qualify", "order", "limit"):
                if node.args.get(clause) is not None:
                    edges(node.args[clause], scope, row_consumer, "ROWSET", clause.upper())
            for join in node.args.get("joins", []):
                if join.args.get("on") is not None:
                    edges(join.args["on"], scope, row_consumer, "ROWSET", "JOIN_ON")
            # Even constant/no-column WHERE changes rows; retain full expression.
            if windows or any(node.args.get(k) for k in ("where", "joins", "group", "having", "qualify", "limit", "distinct")):
                gap("ROWSET_EQUIVALENCE_UNVERIFIED", scope)
        if isinstance(tree, exp.Insert):
            target = tree.this
            result["writes"].append({"statement": statement, "target": target.sql(dialect=dialect),
                "root_ports": [p["port"] for p in result["ports"] if p["root"] and p["port"]["statement"] == statement],
                "physical_binding": "TARGET_SCHEMA_REQUIRED"})
    return result


def compose_demands(snapshots, links, protected_outputs):
    """Propagate only observed structural edges and explicit snapshot contracts.

    All protected outputs include row semantics. Missing, ambiguous and cyclic
    bindings produce boundaries, never empty demands or deletion permissions.
    """
    ports, incoming, rows, by_source = {}, defaultdict(list), defaultdict(list), defaultdict(list)
    unknowns, demands, witnesses = [], [], []
    cases_by_port, observed_cases = defaultdict(list), {}
    for snapshot in snapshots:
        unknowns.extend(deepcopy(snapshot.get("unknowns", [])))
        for row in snapshot["ports"]:
            key = _key(row["port"])
            if key in ports:
                raise ValueError("Duplicate structural port identity")
            ports[key] = row
        for case in snapshot.get("cases", []):
            cases_by_port[_key(case["consumer"])].append(case)
        for edge in snapshot["relations"]:
            incoming[_key(edge["consumer"])].append(edge)
        for edge in snapshot.get("row_relations", []):
            c = edge["consumer"]
            rows[(c["snapshot"], c["statement"], c["scope"])].append(edge)
    for link in links:
        if (not link.get("evidence") or link.get("binding_status") not in {
                "EXPLICIT_VIRTUAL_SLOT", "VERIFIED_SCHEMA_SLOT"} or "partition" not in link):
            raise ValueError("Cross-snapshot link requires explicit slot evidence, partition and binding status")
        if _key(link["producer_port"]) not in ports:
            raise ValueError("Cross-snapshot producer port does not exist")
        by_source[_key(link["consumer_source"])].append(link)

    def visit(port, demand, trail, seen):
        identity = _key(port)
        if identity in seen:
            unknowns.append({"code": "CYCLE_BOUNDARY", "port": port, "demand": demand})
            return
        if identity not in ports and port.get("operator") == "ROW_SEMANTICS":
            for edge in rows[(port["snapshot"], port["statement"], port["scope"])]:
                transfer(edge, {"kind": "ROW_SET", "role": "ROWSET"}, trail, seen | {identity})
            return
        if identity not in ports:
            unknowns.append({"code": "PROTECTED_OR_PRODUCER_PORT_MISSING", "port": port})
            return
        seen = seen | {identity}
        edges = incoming.get(identity, [])
        row = ports[identity]
        for case in cases_by_port.get(identity, ()):
            observed_cases.setdefault((identity, case["id"]), case)
        if not edges and not row.get("constant") and not row.get("observes_rows"):
            unknowns.append({"code": "LOCAL_RELATION_MISSING", "port": port, "demand": demand})
        for edge in edges:
            transfer(edge, demand, trail, seen)
        for edge in rows[(port["snapshot"], port["statement"], port["scope"])]:
            transfer(edge, {"kind": "WHOLE_VALUE", "role": "ROWSET"}, trail, seen)

    def transfer(edge, requested, trail, seen):
        demand = deepcopy(requested)
        operations = edge.get("operations", [])
        generator_input = edge["clause"] == "GENERATOR_INPUT"
        case_control = edge["clause"] == "SELECT" and edge["role"] == "CONDITION"
        if generator_input or case_control:
            demand = {"kind": "WHOLE_VALUE", "downstream_demand": demand}
        if any(op["kind"] == "ROW_SOURCE" for op in operations):
            demand = {"kind": "ROW_SET", "role": "ROWSET"}
        # Only extractions before the first path boundary describe the input.
        path_boundary_index = next((i for i, op in enumerate(operations)
                                    if op["kind"] in {"COMPARISON", "ARITHMETIC"} or
                                    (op["kind"] == "TRANSFORM" and op.get("name") == "REGEXP_EXTRACT")), None)
        input_operations = operations[:path_boundary_index]
        extracts = [op["path_tokens"] for op in input_operations if op["kind"] == "EXTRACT"]
        if extracts:
            demand = {"kind": "VALUE_PATH", "path_tokens": extracts[0],
                      "operation_chain": deepcopy(operations), "downstream_demand": demand}
        if any(op["kind"].startswith("OPAQUE") for op in operations):
            demand["opaque_boundary"] = True
        # Observation of an input is not an inverse semantic contract for a
        # transform. Preserve the observed path but widen the demand kind.
        if (not case_control and requested.get("kind") == "UNKNOWN") or any(op["kind"] in {
                "CAST", "AGGREGATE", "TRANSFORM", "COMPARISON", "ARITHMETIC", "OPAQUE_FUNCTION",
                "OPAQUE_PATH", "UNION_BRANCH", "WINDOW", "GENERATOR"}
               for op in operations):
            original_demand = deepcopy(demand)
            demand = {"kind": "UNKNOWN", "reason": "TRANSFORM_SEMANTICS_UNVERIFIED",
                      "operation_chain": deepcopy(operations), "downstream_demand": original_demand}
            if extracts:
                demand["path_tokens"] = extracts[0]
                demand["path_basis"] = "OBSERVED_INPUT_ONLY"
            elif path_boundary_index is None and "path_tokens" in original_demand:
                demand["path_tokens"] = deepcopy(original_demand["path_tokens"])
                demand["path_basis"] = "OBSERVED_INPUT_ONLY"
        role = requested.get("role", edge["role"])
        if case_control and role != "ROWSET":
            role = "CONDITION"
        elif generator_input and role not in {"ROWSET", "CONDITION"}:
            role = "STRUCTURE"
        demand["role"] = role
        step = deepcopy(edge)
        witnesses.append(step)
        if "producer" in edge:
            visit(edge["producer"], demand, trail + [step], seen)
            return
        source = edge["source"]
        matches = by_source.get(_key(source), [])
        if not matches:
            demands.append({**demand, "source": deepcopy(source), "witness": trail + [step]})
            return
        if len(matches) > 1:
            unknowns.append({"code": "MULTIPLE_WRITERS", "source": source, "candidates": deepcopy(matches)})
            demands.append({"kind": "UNKNOWN", "source": source, "reason": "MULTIPLE_WRITERS"})
            return
        link = matches[0]
        witnesses.append({"kind": "CROSS_SNAPSHOT_CONTRACT", **deepcopy(link)})
        visit(link["producer_port"], demand, trail + [step, deepcopy(link)], seen)

    for protected in protected_outputs:
        visit(protected["port"], protected.get("demand", {"kind": "WHOLE_VALUE"}), [], set())
    return {"status": "REVIEW_ONLY", "rowset_verified": False,
        "protected_outputs": deepcopy(protected_outputs), "include_row_semantics": True,
        "source_demands": demands, "observed_relations": witnesses, "unknowns": unknowns,
        "observed_cases": deepcopy(list(observed_cases.values())),
        "observed_windows": [{"snapshot": s["snapshot_id"], "sql_sha256": s["sql_sha256"], **deepcopy(w)}
                             for s in snapshots for w in s.get("windows", [])],
        "coverage_boundary": {"scope": "EXPLICIT_SNAPSHOT_SUBGRAPH", "all_consumers_verified": False,
                              "physical_schema_verified": False, "pruning_authorized": False}}
