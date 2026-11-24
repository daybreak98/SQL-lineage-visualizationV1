"""An opt-in extension of the offline binding observer; never imported by the API."""
import re

from sqlglot import exp

from app.services.subfield import only_projection_args
from experiments.binding_shadow import CLOSER, SELECT_ARGS, TABLE_ARGS, WHERE, Shadow, span

ON = re.compile(r"\s*(ON)\b", re.I)
MAX_STAGES = 32
MAX_TESTS = 32


class InnerShadow(Shadow):
    def __init__(self, *args):
        super().__init__(*args)
        self.snapshot["rules"] = "binding-shadow-inner-2"

    def table_ok(self, ref):
        return (type(ref) is exp.Table and not ref.alias_column_names
                and only_projection_args(ref, TABLE_ARGS)
                and all(self.anchored(p) for p in ref.parts)
                and (not ref.alias or self.anchored(ref.args["alias"].this)))

    def equality_shape(self, expr, anchor):
        # Check operator scope and traversal budget without using operand
        # resolution as a precondition for the visibility of a sibling.
        todo, count = [expr], 0
        while todo:
            node = todo.pop()
            count += 1
            if count > 2 * MAX_TESTS - 1:
                self.limit("JOIN_PREDICATE_BUDGET", anchor)
                return False
            if type(node) is exp.And:
                todo.extend((node.expression, node.this))
            elif type(node) is not exp.EQ:
                return False
        return True

    def stages(self, q):
        """Yield prefixes of the actual flat FROM/Join operator list, never a subtree walk."""
        frm = q.args.get("from_")
        if (type(q) is not exp.Select or not only_projection_args(q, SELECT_ARGS | {"joins"})
                or not frm or not self.table_ok(frm.this)):
            return
        prefix = [frm.this]
        names = {frm.this.alias_or_name.casefold()}
        for ordinal, j in enumerate(q.args.get("joins") or (), 1):
            ref = j.this
            if (ordinal > MAX_STAGES or type(j) is not exp.Join or j.parent is not q
                    or not only_projection_args(j, {"this", "kind", "on"})
                    or j.kind not in ("", "INNER") or j.args.get("on") is None
                    or not self.table_ok(ref) or ref.alias_or_name.casefold() in names):
                return
            # A comma relation normalized to Join is not an explicit JOIN.
            start = self.anchored(ref.parts[0])[0]
            i = start
            while i and self.sql[i-1].isspace():
                i -= 1
            if (i < 4 or self.sql[i-4:i].upper() != "JOIN"
                    or (i > 4 and (self.sql[i-5].isalnum() or self.sql[i-5] == "_"))):
                return
            decl = self.anchored(ref.args["alias"].this if ref.alias else ref.this)
            token = ON.match(self.sql, decl[1])
            if not token or not self.equality_shape(j.args["on"], token.span(1)):
                return
            prefix.append(ref)
            names.add(ref.alias_or_name.casefold())
            yield ordinal, j, token.span(1), tuple(prefix)

    def where_anchor(self, q):
        if not q.args.get("joins"):
            return super().where_anchor(q)
        # Exact end of the final supported ON operand, not the first WHERE
        # substring in the input (which could be inside a string/subquery).
        node = q.args["joins"][-1].args.get("on")
        while type(node) in (exp.And, exp.EQ):
            node = node.expression
        if type(node) is exp.Column:
            end = self.anchored(node.this)
        elif type(node) is exp.Literal:
            end = span(node)
        elif type(node) in (exp.JSONExtract, exp.JSONExtractScalar):
            literal = node.expression.meta.get("json_path_position")
            closer = CLOSER.match(self.sql, literal["end"]) if literal else None
            end = closer.span() if closer else None
        else:
            return None
        match = WHERE.match(self.sql, end[1]) if end else None
        return match.span(1) if match else None

    def bound(self, a, col, scope, clause, ref, source, producer):
        q = scope.expression
        joins = q.args.get("joins")
        if not joins:
            return super().bound(a, col, scope, clause, ref, source, producer)
        st, sc, pos = a.statement, a.scope_ids[scope], self.anchored(col.this)
        # Ascend to the actual ON owner; a column from a subquery cannot be borrowed.
        owner = col.find_ancestor(exp.Join) if clause == "JOIN" else None
        if clause not in ("JOIN", "SELECT", "WHERE") or col.find_ancestor(exp.Query) is not q:
            self.gap(st, sc, pos, "JOIN_SCOPE_UNVERIFIED")
            return
        for n, join, anchor, visible in self.stages(q):
            at_consumer = (join is owner) if clause == "JOIN" else (n == len(joins))
            if not at_consumer:
                continue
            # Limit the candidates to this prefix FIRST. Then test uniqueness
            # and identity against the resolver's actual relation (no re-binding).
            matches = [v for v in visible if col.table and v.alias_or_name.casefold() == col.table.casefold()]
            if len(matches) == 1 and matches[0] is ref and not col.db and not col.catalog:
                if clause == "JOIN":
                    operand = col.parent if type(col.parent) in (exp.JSONExtract, exp.JSONExtractScalar) else col
                    conjunct = operand.parent
                    if type(conjunct) is exp.EQ:
                        while type(conjunct.parent) is exp.And:
                            conjunct = conjunct.parent
                    if type(operand.parent) is not exp.EQ or conjunct is not join.args["on"]:
                        self.gap(st, sc, pos, "JOIN_OPERAND_UNVERIFIED")
                        return
                super().bound(a, col, scope, clause, ref, source, producer, stage=(n, anchor))
                o = self.key("O", st, sc, pos)
                ob = self.records.get(o, {})
                if ob.get("kind") == "COLUMN_BINDING" and ob.get("join_stage") == n:
                    decls = [self.anchored(v.args["alias"].this if v.alias else v.this) for v in visible]
                    self.put(self.key("V", st, sc, pos), ob["group"], kind="JOIN_USE_VISIBLE",
                             occurrence=o, relation=ob["relation"], ordinal=n, anchor=anchor,
                             clause=clause, prefix_declarations=decls)
                return
            self.gap(st, sc, pos, "JOIN_OCCURRENCE_NOT_VISIBLE_OR_QUALIFIED")
            return
        self.gap(st, sc, pos, "JOIN_STAGE_UNSUPPORTED")

    def extract(self, a, call, tokens, scope, role, clause):
        if clause == "JOIN":
            # A located literal demand alone establishes neither visibility nor lineage.
            return super().extract(a, call, tokens, scope, "CONDITION", clause, join_local=True)
        return super().extract(a, call, tokens, scope, role, clause)

    def predicate(self, st, sc, node):
        """Admit a bounded conjunction of equalities over original operands."""
        todo, controls, reads, literals, count = [node], [], [], [], 0
        while todo:
            test = todo.pop()
            count += 1
            if count > 2 * MAX_TESTS - 1:
                self.limit("JOIN_PREDICATE_BUDGET", next((span(n) for n in test.walk() if span(n)), None))
                return None
            if type(test) is exp.And:
                todo.extend((test.expression, test.this))
                continue
            if type(test) is not exp.EQ:
                return None
            for operand in (test.this, test.expression):
                if type(operand) is exp.Literal and span(operand):
                    literals.append(span(operand))
                    continue
                col = operand
                if type(operand) in (exp.JSONExtract, exp.JSONExtractScalar):
                    reads.append(self.key("read", st, sc, span(operand)))
                    col = operand.this
                if type(col) is not exp.Column or not col.table or not self.anchored(col.this):
                    return None
                controls.append(self.key("O", st, sc, self.anchored(col.this)))
        return controls, reads, literals

    def finish_query(self, ctx):
        plain = {scope: sc for scope, sc in ctx["scope_ids"].items() if not scope.expression.args.get("joins")}
        super().finish_query({**ctx, "scope_ids": plain})
        st = ctx["statement"]
        for scope, sc in ctx["scope_ids"].items():
            q = scope.expression
            if scope in plain:
                continue
            accepted = 0
            for n, join, anchor, prefix in self.stages(q):
                parts = self.predicate(st, sc, join.args["on"])
                if parts is None:
                    self.gap(st, sc, anchor, "JOIN_PREDICATE_UNVERIFIED")
                    break
                controls, reads, literals = parts
                inputs = [self.relation(st, sc, ref) for ref in prefix]
                self.put(self.key("J", st, sc, n), "row_effects", kind="INNER_ON_STAGE",
                         anchor=anchor, ordinal=n, inputs=inputs, controls=controls, reads=reads,
                         literals=literals, previous=self.key("J", st, sc, n-1) if n > 1 else None,
                         reason="ROWSET_EQUIVALENCE_UNVERIFIED")
                accepted = n
            if accepted != len(q.args["joins"]):
                next_ref = q.args["joins"][accepted].this
                a = span(next_ref.this) if type(next_ref) is exp.Table else span(next_ref)
                if accepted >= MAX_STAGES:
                    self.limit("JOIN_STAGE_BUDGET", a)
                self.gap(st, sc, a, "JOIN_STAGE_UNSUPPORTED")
            if q.args.get("where") is not None:
                anchor = self.where_anchor(q)
                if not anchor:
                    self.gap(st, sc, None, "FILTER_ANCHOR_UNVERIFIED")
                self.put(self.key("FILTER", st, sc), "row_effects", kind="FILTER", anchor=anchor,
                         scope=sc, reason="ROWSET_EQUIVALENCE_UNVERIFIED")

    def retained_stage(self, stage):
        if stage["previous"] and self.records.get(stage["previous"], {}).get("kind") != "INNER_ON_STAGE":
            return False
        if not all(self.records.get(r, {}).get("kind") == "ROW_INPUT" for r in stage["inputs"]):
            return False
        for o in stage["controls"]:
            ob = self.records.get(o, {})
            if (ob.get("kind") != "COLUMN_BINDING" or ob["clause"] != "JOIN"
                    or ob.get("join_stage") != stage["ordinal"] or ob["operator_span"] != stage["anchor"]
                    or ob["relation"] not in stage["inputs"] or not ob["qualifier"]
                    or self.records.get(self.key("V", *o[2:]), {}).get("kind") != "JOIN_USE_VISIBLE"):
                return False
        for read in stage["reads"]:
            local = self.records.get(read, {})
            if local.get("kind") != "LOCAL_EXTRACT" or local["input"] not in stage["controls"]:
                return False
        return True

    def export(self, parsed):
        # Collection may evict prerequisites after the ON callback. Seal each
        # prefix against FINAL records; no new record may evict a checked edge.
        self.collecting = False
        # A V certifies only one use. Seal it before row-stage certificates.
        for k in [k for k in self.records if k[1] == "V"]:
            v = self.records[k]
            if v.get("kind") != "JOIN_USE_VISIBLE":
                continue
            ob = self.records.get(v["occurrence"], {})
            if (not parsed or ob.get("kind") != "COLUMN_BINDING" or not ob["qualifier"]
                    or ob.get("join_stage") != v["ordinal"] or ob["relation"] != v["relation"]
                    or self.records.get(v["relation"], {}).get("kind") != "ROW_INPUT"):
                self.bytes -= self.size(k, self.records.pop(k))
                self.gap(k[2], k[3], k[4], "JOIN_USE_VISIBILITY_UNVERIFIED")
        for k in sorted(k for k in self.records if k[1] == "J"):
            v = self.records[k]
            if v.get("kind") == "INNER_ON_STAGE" and (not parsed or not self.retained_stage(v)):
                self.bytes -= self.size(k, self.records.pop(k))
                self.gap(k[2], k[3], v["anchor"], "JOIN_STAGE_NOT_CERTIFIED")
        for k in [k for k in self.records if k[1] == "P"]:
            ob = self.records.get(self.records[k].get("input"), {})
            if "join_stage" in ob:
                stage = self.key("J", k[2], k[3], ob["join_stage"])
                use = self.key("V", *self.records[k]["input"][2:])
                if (self.records.get(stage, {}).get("kind") != "INNER_ON_STAGE"
                        or self.records.get(use, {}).get("kind") != "JOIN_USE_VISIBLE"):
                    self.bytes -= self.size(k, self.records.pop(k))
                    self.gap(k[2], k[3], ob["anchor"], "JOIN_TRANSFER_UNVERIFIED")
        return super().export(parsed)
