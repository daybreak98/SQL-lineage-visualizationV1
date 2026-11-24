"""Per-parse evidence for offline experiments. Never imported by the public route."""
from dataclasses import dataclass, fields
from hashlib import sha256
import json
import re
from uuid import uuid4

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.services.subfield import Analysis, only_projection_args


GROUPS = ("value_edges", "control_uses", "row_effects", "gaps")
SELECT_ARGS = {"with_", "from_", "expressions", "where"}
TABLE_ARGS = {"this", "db", "catalog", "alias"}
WHERE = re.compile(r"\s*(WHERE)\b", re.I)
CLOSER = re.compile(r"\s*\)")


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


@dataclass(frozen=True)
class Limits:
    tokens: int = 32
    paths: int = 64
    depth: int = 32
    refs: int = 128
    edges: int = 4096
    memo_bytes: int = 2 * 1024 * 1024

    def __post_init__(self):
        for f in fields(self):
            v = getattr(self, f.name)
            if type(v) is not int or not 0 <= v <= f.default:
                raise ValueError(f"{f.name} must be between zero and {f.default}")


def span(node):
    if node is not None:
        m = node.meta
        if type(m.get("start")) is int and type(m.get("end")) is int:
            return m["start"], m["end"] + 1


def order(anchor):
    return anchor if anchor is not None else (float("inf"), float("inf"))


class Shadow:
    def __init__(self, sql, dialect, schemas, limits):
        self.sql, self.limits = sql, limits
        self.sid = uuid4().hex
        self.snapshot = dict(id=self.sid, sql_sha256=sha256(sql.encode()).hexdigest(), dialect=dialect,
                             sqlglot=sqlglot.__version__, rules="binding-shadow-2",
                             schema_sha256=sha256(wire(schemas)).hexdigest())
        self.records = {}
        self.paths, self.expanded = {}, {}
        self.first_limit, self.bytes = None, 0
        self.cutoff, self.collecting = None, True

    def key(self, kind, *parts):
        return (self.sid, kind, *parts)

    def limit(self, reason, anchor):
        if self.first_limit is None or order(anchor) < order(self.first_limit["anchor"]):
            self.first_limit = dict(reason=reason, anchor=anchor)

    @staticmethod
    def size(key, value):
        return len(wire(key)) + len(wire(value))

    @staticmethod
    def rank(key, rec):
        return order(rec["anchor"]), key[1], wire(key)

    def put(self, key, group, **fields):
        rec = dict(group=group, **fields)
        old = self.records.get(key)
        if old == rec:
            return True
        if old is not None:
            if old.get("reason") == "ANCHOR_CONFLICT":
                return False
            self.bytes -= self.size(key, old)
            del self.records[key]
            rec = dict(group="gaps", reason="ANCHOR_CONFLICT", anchor=rec["anchor"])
        size = self.size(key, rec)
        rank = None
        if self.collecting and self.cutoff is not None:
            rank = self.rank(key, rec)
            if rank >= self.cutoff:
                self.limit("EDGE_OR_BYTE_BUDGET", rec["anchor"])
                return False
        # AST callbacks are topological, not lexical. Under pressure keep a
        # bounded original-order prefix; never admit records past its first hole.
        while len(self.records) >= self.limits.edges or self.bytes + size > self.limits.memo_bytes:
            if self.collecting and rank is None:
                rank = self.rank(key, rec)
            if self.collecting and self.records:
                last = max(self.records, key=lambda k: self.rank(k, self.records[k]))
                victim = self.records[last]
                last_rank = self.rank(last, victim)
                if last_rank > rank:
                    self.cutoff = last_rank
                    self.limit("EDGE_OR_BYTE_BUDGET", victim["anchor"])
                    self.bytes -= self.size(last, self.records.pop(last))
                    continue
            if self.collecting:
                self.cutoff = rank
            self.limit("EDGE_OR_BYTE_BUDGET", rec["anchor"])
            return False
        self.records[key] = rec
        self.bytes += size
        return group == rec["group"]

    def gap(self, st, sc, anchor, reason):
        self.put(self.key("gap", st, sc, anchor, reason), "gaps", anchor=anchor, reason=reason)

    def anchored(self, ident):
        p = span(ident)
        if type(ident) is exp.Identifier and p and self.sql[slice(*p)] == ident.name:
            return p

    def where_anchor(self, q):
        frm = q.args.get("from_")
        ref = frm.this if frm is not None else None
        if type(ref) is exp.Table and not ref.alias_column_names:
            end = self.anchored(ref.args["alias"].this if ref.alias else ref.this)
            match = WHERE.match(self.sql, end[1]) if end else None
            if match:
                return match.span(1)

    def relation(self, st, sc, ref):
        decl = self.anchored(ref.args["alias"].this if ref.alias else ref.this)
        parts = [self.anchored(p) for p in ref.parts]
        if not decl or not parts or not all(parts):
            return None
        r = self.key("R", st, sc, decl)
        self.put(r, "row_effects", kind="ROW_INPUT", anchor=decl, name=ref.alias_or_name,
                 source=".".join(p.name for p in ref.parts), parts=parts)
        return r

    def bound(self, a, col, scope, clause, ref, source, producer, *, stage=None):
        st, sc, q = a.statement, a.scope_ids[scope], scope.expression
        pos = self.anchored(col.this)
        selected = scope.selected_sources
        frm = q.args.get("from_")
        if (type(q) is not exp.Select or frm is None
                or (stage is None and (frm.this is not ref or len(selected) != 1
                                      or not only_projection_args(q, SELECT_ARGS)))
                or type(ref) is not exp.Table or not only_projection_args(ref, TABLE_ARGS)
                or ref.alias_column_names or col.find_ancestor(exp.Query) is not q
                or (stage is None and clause not in ("SELECT", "WHERE")) or a.macro_context is not None):
            self.gap(st, sc, pos, "INPUT_SCOPE_NOT_CERTIFIED")
            return
        parts = [self.anchored(p) for p in col.parts]
        r = self.relation(st, sc, ref)
        if not pos or not r or not all(parts):
            self.gap(st, sc, pos, "MISSING_ANCHOR")
            return
        # Veto duplicate/recursive declarations or a lexical name colliding
        # with a presumed base table. Never choose a source by this audit.
        parent = q
        while parent is not None and not ref.db and not ref.catalog:
            with_ = parent.args.get("with_")
            if with_:
                matches = [cte for cte in with_.expressions if cte.alias.lower() == ref.name.lower()]
                if matches:
                    if (len(matches) != 1 or with_.args.get("recursive") or producer is None
                            or matches[0].this is not source.expression
                            or not self.anchored(matches[0].args["alias"].this)):
                        self.gap(st, sc, pos, "CTE_DECLARATION_UNVERIFIED")
                        return
                    break
            parent = parent.parent
        if producer is not None:
            if (not source.is_cte or ref.db or ref.catalog or source in a.open_scopes
                    or type(source.expression) is not exp.Select or source.outer_columns
                    or any(i.is_star for i in source.expression.selects)):
                self.gap(st, sc, pos, "PRODUCER_UNVERIFIED")
                return
            endpoint = self.key("P", st, producer["scope"], producer["slot"])
        elif source is ref:
            endpoint = self.key("BASE", r, col.name)
        else:
            self.gap(st, sc, pos, "NON_BASE_TERMINAL")
            return

        oper = self.where_anchor(q) if clause == "WHERE" else pos
        if stage and clause == "JOIN":
            oper = stage[1]
        if not oper or (clause == "SELECT" and col.find_ancestor(exp.Case, exp.If) is not None):
            self.gap(st, sc, pos, "CONSUMER_NOT_CERTIFIED")
            return
        o = self.key("O", st, sc, pos)
        self.put(o, "value_edges" if clause == "SELECT" else "control_uses",
                 kind="COLUMN_BINDING", anchor=pos, qualifier=self.anchored(col.args.get("table")),
                 relation=r, endpoint=endpoint, column=col.name, clause=clause,
                 role="VALUE" if clause == "SELECT" else "CONDITION", operator_span=oper,
                 operand=(parts[0][0], pos[1]), **({"join_stage": stage[0]} if stage else {}))
        item = col.parent if type(col.parent) is exp.Alias else col
        if item.parent is q and item.arg_key == "expressions" and item.index is not None:
            self.put(self.key("P", st, sc, item.index+1), "value_edges",
                     kind="COLUMN_PASSTHROUGH", anchor=pos, input=o)

    def extract(self, a, call, tokens, scope, role, clause, *, join_local=False):
        st, sc = a.statement, a.scope_ids[scope]
        cp, col = span(call), call.this
        lp = call.expression.meta.get("json_path_position")
        if (type(col) is not exp.Column or not lp or not cp or not tokens
                or a.macro_context is not None or (clause not in ("SELECT", "WHERE") and not join_local)
                or self.sql[slice(*cp)].lower() != "get_json_object"):
            self.gap(st, sc, cp, "EXTRACTION_NOT_CERTIFIED")
            return
        parts = [self.anchored(p) for p in col.parts]
        literal = lp["start"], lp["end"]
        close = CLOSER.match(self.sql, literal[1])
        if (not all(parts) or not close or not cp[1] <= parts[0][0] < parts[-1][1] <= literal[0]
                or not re.fullmatch(r"\s*\(\s*", self.sql[cp[1]:parts[0][0]])
                or not re.fullmatch(r"\s*,\s*", self.sql[parts[-1][1]:literal[0]])):
            self.gap(st, sc, cp, "EXTRACTION_ANCHOR_UNVERIFIED")
            return
        group = "value_edges" if clause == "SELECT" and role == "VALUE" else "control_uses"
        site = dict(anchor=cp, operator_span=(cp[0], close.end()), operand=(parts[0][0], parts[-1][1]),
                    literal=literal, input=self.key("O", st, sc, parts[-1]), role=role, clause=clause)
        key = self.key("read", st, sc, cp)
        if len(tokens) > self.limits.tokens:
            self.limit("PATH_TOKEN_BUDGET", cp)
            self.put(key, group, kind="LOCAL_EXTRACT_SITE", **site)
        else:
            self.put(key, group, kind="LOCAL_EXTRACT", path=tokens, **site)

    def abort_query(self, st):
        # Keep located demands for diagnostics; only completed statements may
        # advance them. The shorter tag cannot overrun the memo budget.
        for key, rec in self.records.items():
            if key[1] == "read" and key[2] == st and rec.get("kind") == "LOCAL_EXTRACT":
                self.bytes -= len("LOCAL_EXTRACT") - len("LOCAL_SITE")
                rec["kind"] = "LOCAL_SITE"

    def finish_query(self, ctx):
        st = ctx["statement"]
        for scope, sc in ctx["scope_ids"].items():
            q = scope.expression
            if type(q) is not exp.Select or not only_projection_args(q, SELECT_ARGS):
                self.gap(st, sc, span(q), "UNSUPPORTED_ROW_OPERATOR")
                continue
            frm = q.args.get("from_")
            if frm and type(frm.this) is exp.Table and only_projection_args(frm.this, TABLE_ARGS):
                self.relation(st, sc, frm.this)
            if q.args.get("where") is not None:
                anchor = self.where_anchor(q)
                if not anchor:
                    self.gap(st, sc, None, "FILTER_ANCHOR_UNVERIFIED")
                self.put(self.key("FILTER", st, sc), "row_effects", kind="FILTER", anchor=anchor,
                         scope=sc, reason="ROWSET_EQUIVALENCE_UNVERIFIED")

    def remember(self, memo, key, member, bound, reason, anchor):
        # Account serialized key once, plus exact UTF-8 length of the value
        # array (brackets and commas included); no cross-snapshot caches.
        bucket = memo.get(key)
        if bucket is not None and member in bucket:
            return True
        if (len(bucket) if bucket else 0) >= bound:
            self.limit(reason, anchor)
            return False
        size = len(wire(member)) + (1 if bucket else len(wire(key)) + 2)
        if self.bytes + size > self.limits.memo_bytes:
            self.limit("MEMO_BYTE_BUDGET", anchor)
            return False
        memo.setdefault(key, set()).add(member)
        self.bytes += size
        return True

    def conclude(self, key, read):
        st, sc, anchor = key[2:]
        domain = "CONTROL" if read["group"] == "control_uses" else "VALUE"
        trail, seen, hops, stages = [], set(), 0, []
        o = read["input"]
        while o not in seen:
            seen.add(o)
            ob = self.records.get(o, {})
            if ob.get("kind") != "COLUMN_BINDING":
                break
            # A unique resolver choice is local evidence. The strict subset
            # additionally requires an original qualifier at *every* occurrence.
            if ob["qualifier"] is None:
                self.gap(o[2], o[3], ob["anchor"], "QUALIFIER_REQUIRED")
                return
            if "join_stage" in ob:
                stage = self.key("V", *o[2:])
                if self.records.get(stage, {}).get("kind") != "JOIN_USE_VISIBLE":
                    self.gap(st, sc, anchor, "JOIN_USE_VISIBILITY_UNVERIFIED")
                    return
                if stage not in stages:
                    stages.append(stage)
            r, endpoint = ob["relation"], ob["endpoint"]
            if self.records.get(r, {}).get("kind") != "ROW_INPUT":
                break
            if not self.remember(self.paths, (r,endpoint,domain), read["path"], self.limits.paths,
                                 "DISTINCT_PATH_BUDGET", anchor):
                return
            trail.extend((o, r))
            if endpoint[1] == "BASE":
                self.put(self.key("proof", key), read["group"], kind="STRICT_READ", domain=domain,
                         anchor=anchor, local_read=key, dependencies=trail, terminal=endpoint,
                         **({"stage_dependencies": stages} if stages else {}))
                return
            hops += 1
            if hops > self.limits.depth:
                self.limit("DEPTH_BUDGET", anchor)
                return
            if not self.remember(self.expanded, st, r, self.limits.refs, "REFERENCE_BUDGET", anchor):
                return
            port = self.records.get(endpoint, {})
            if port.get("kind") != "COLUMN_PASSTHROUGH":
                break
            trail.append(endpoint)
            o = port["input"]
        self.gap(st, sc, anchor, "VALUE_CHAIN_NOT_CLOSED")

    def export(self, parsed):
        self.collecting = False
        if parsed:
            for k in sorted(self.records, key=lambda k: self.rank(k, self.records[k])):
                rec = self.records[k]
                if rec.get("kind") == "LOCAL_EXTRACT":
                    self.conclude(k, rec)
        else:
            self.gap(None, None, None, "FULL_PARSE_UNVERIFIED")
        out = dict(snapshot=self.snapshot, budget_gap=self.first_limit,
                   usage=dict(records=len(self.records), memo_bytes=self.bytes))
        def binding_retained(key):
            v = self.records.get(key, {})
            return (v.get("kind") == "COLUMN_BINDING"
                    and self.records.get(v["relation"], {}).get("kind") == "ROW_INPUT")

        def transfer_retained(key):
            v = self.records.get(key, {})
            return v.get("kind") == "COLUMN_PASSTHROUGH" and binding_retained(v["input"])

        # These are projections of the final retained records, not new memo
        # entries. Never use a dangling key as a proxy for an unavailable edge.
        out.update({group: [] for group in GROUPS})
        for key, v in self.records.items():
            kind = v.get("kind")
            row = dict(id=key, **v)
            if kind == "COLUMN_BINDING":
                if not binding_retained(key):
                    continue
                endpoint = row["endpoint"]
                if endpoint[1] == "P" and not transfer_retained(endpoint):
                    del row["endpoint"]
                    row["endpoint_gap"] = "PRODUCER_TRANSFER_UNAVAILABLE"
            elif kind == "COLUMN_PASSTHROUGH" and not transfer_retained(key):
                continue
            elif kind in {"LOCAL_EXTRACT", "LOCAL_EXTRACT_SITE", "LOCAL_SITE"}:
                if not binding_retained(row["input"]):
                    del row["input"]
                    row["input_gap"] = "OCCURRENCE_BINDING_UNAVAILABLE"
            out[v["group"]].append(row)
        return out


class ObservedAnalysis(Analysis):
    def __init__(self, sql, dialect, schemas, limits, shadow_type=Shadow):
        super().__init__(sql, dialect, schemas)
        self.shadow_failed = False
        self.shadow = shadow_type(sql, dialect, schemas, limits)
        self.bound_occurrence_observer = lambda *args: self.observe(self.shadow.bound, self, *args)
        self.literal_read_observer = lambda *args: self.observe(self.shadow.extract, self, *args)

    def observe(self, fn, *args):
        if not self.shadow_failed:
            try:
                fn(*args)
            except Exception:
                self.shadow_failed = True

    def query(self, query, target, *, check_projection=False):
        try:
            result = super().query(query, target, check_projection=check_projection)
        except SqlglotError:
            self.observe(self.shadow.abort_query, self.statement)
            raise
        self.observe(self.shadow.finish_query, {"statement": self.statement, "scope_ids": self.scope_ids})
        return result

    def unknown(self, code, node, clause=None, inputs=()):
        super().unknown(code, node, clause, inputs)
        self.observe(self.shadow.gap, self.statement, getattr(self, "current_scope_id", None), span(node), code)


def offline_analyze(sql, dialect="spark", schemas=None, *, enabled=False, limits=Limits(), inner_joins=False):
    """Return (unchanged public facts, private graph or None). No HTTP switch."""
    if not enabled:
        return Analysis(sql, dialect, schemas).run(), None
    unavailable = {**{k: [] for k in GROUPS}, "gaps": [{"reason": "SHADOW_UNAVAILABLE"}]}
    try:
        if inner_joins:
            from experiments.inner_shadow import InnerShadow
            shadow_type = InnerShadow
        else:
            shadow_type = Shadow
        analysis = ObservedAnalysis(sql, dialect, schemas, limits, shadow_type)
    except Exception:
        return Analysis(sql, dialect, schemas).run(), unavailable
    public = analysis.run()
    if not analysis.shadow_failed:
        try:
            return public, analysis.shadow.export(public["coverage"]["parsed"])
        except Exception:
            pass
    return public, unavailable
