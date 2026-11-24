"""Offline Spark SELECT witness for a single CTE output. Not a public identity wire."""
from collections import defaultdict
from copy import deepcopy
import re

from sqlglot import exp

from app.services.subfield import analyze_subfields, only_projection_args
from experiments.binding_shadow import Limits, ObservedAnalysis, span


NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
VERSION = "single-cte-name-shadow:1"


def position(value):
    return (value["start"], value["end"]) if value else None


class Capture(ObservedAnalysis):
    root = None

    def query(self, query, target, *, check_projection=False):
        super().query(query, target, check_projection=check_projection)
        if check_projection and target is None:  # actual complete, single SELECT
            self.root = query

    def token(self, ident):
        if type(ident) is exp.Identifier and not ident.quoted and NAME.fullmatch(ident.name):
            return self.shadow.anchored(ident)

    def witnesses(self, facts):
        q = self.root
        if (q is None or len(self.scope_ids) != 2 or not only_projection_args(q, {"with_","expressions","from_"})
                or len(q.selects) > 64 or self.shadow_failed or self.shadow.first_limit
                or not facts["coverage"]["parsed"] or facts["coverage"]["partial"]):
            return []
        with_ = q.args.get("with_")
        if not with_ or not only_projection_args(with_, {"expressions"}) or len(with_.expressions) != 1:
            return []
        cte, = with_.expressions
        if (not only_projection_args(cte, {"this","alias"}) or cte.alias_column_names
                or not (cte_name := self.token(cte.args["alias"].this))):
            return []
        by_ast = {id(scope.expression):scope for scope in self.scope_ids}
        root, src = by_ast.get(id(q)), by_ast.get(id(cte.this))
        if (root is None or not root.is_root or src is None or not src.is_cte
                or type(cte.this) is not exp.Select or not only_projection_args(cte.this, {"from_","expressions"})
                or len(cte.this.selects) > 64):
            return []
        # Use the same Scope objects used by the main resolver; names are vetoes, never a lookup strategy.
        decls = []
        for scope, expected in ((root, src), (src, None)):
            selected = scope.selected_sources
            if len(selected) != 1:
                return []
            ref, bound = next(iter(selected.values()))
            if (type(ref) is not exp.Table or ref is not scope.expression.args["from_"].this
                    or bound is not (expected if expected is not None else ref)
                    or not only_projection_args(ref, {"this","db","catalog","alias"})
                    or ref.alias_column_names or not all(self.token(p) for p in ref.parts)):
                return []
            decl = self.token(ref.args["alias"].this if ref.alias else ref.this)
            if not decl:
                return []
            decls.append((self.shadow.key("R", self.statement, self.scope_ids[scope], decl), ref))

        (local_rel, local_ref), (base_rel, base_ref) = decls
        if local_ref.db or local_ref.catalog or local_ref.name.lower() != cte.alias.lower():
            return []
        st, sc = self.statement, self.scope_ids[root]
        uses, roots = defaultdict(list), defaultdict(list)
        for i,u in enumerate(facts["uses"]):
            uses[u["statement"], position(u.get("position"))].append((i,u))
        for m in facts["mappings"]:
            if m.get("root") and m.get("target") is None:
                roots[m["statement"],m["scope"],m["slot"]].append(position(m.get("position")))
        record = self.shadow.records.get
        key = self.shadow.key
        output_names = [i.alias_or_name.lower() for i in cte.this.selects]
        local_names = {i.alias.lower() for i in q.selects if i.alias}
        result = []
        for slot,item in enumerate(q.selects, 1):
            if type(item) is not exp.Alias or not (owner := self.token(item.args["alias"])):
                continue
            call = item.this
            read = record(key("read",st,sc,span(call)), {})
            native = uses[st, span(call)]
            if (type(call) not in (exp.JSONExtract, exp.JSONExtractScalar) or read.get("kind") != "LOCAL_EXTRACT"
                    or read["clause"] != "SELECT" or read["role"] != "VALUE"
                    or len(native) != 1 or roots[st,sc,slot] != [owner]):
                continue
            i,u = native[0]
            col = call.this
            if (type(col) is not exp.Column or col.db or col.catalog or not self.token(col.this)
                    or u.get("kind") != "EXTRACT" or u.get("path_derivation")
                    or (u["role"],u["clause"]) != ("VALUE","SELECT")
                    or position(u.get("json_path_position")) != read["literal"]
                    or u["path_tokens"] != [dict(kind=k,value=v) for k,v in read["path"]]):
                continue
            occ = record(read["input"], {})
            if (occ.get("kind") != "COLUMN_BINDING" or occ["relation"] != local_rel
                    or occ["anchor"] != self.token(col.this)):
                continue
            # Only the actual resolver-provided output port can advance. A unique
            # table name or a matching flattened public source cannot supply it.
            port = occ["endpoint"]
            if port[:-1] != key("P", st, self.scope_ids[src]) or not 1 <= port[-1] <= len(output_names):
                continue
            name = col.name.lower()
            if output_names.count(name) != 1 or output_names[port[-1]-1] != name:
                continue
            anchor = {"column_span":occ["anchor"]}
            if col.table:
                if (not occ["qualifier"] or occ["qualifier"] != self.token(col.args["table"])
                        or col.table.lower() != local_ref.alias_or_name.lower()):
                    continue
                anchor.update(kind="QUALIFIED_COLUMN", qualifier_span=occ["qualifier"])
            elif len(col.parts)==1 and occ["qualifier"] is None and name not in local_names:
                anchor.update(kind="SINGLE_INPUT_OUTPUT_NAME")  # no qualifier token in the SQL
            else:
                continue
            out = cte.this.selects[port[-1]-1]
            transfer = record(port, {})
            if (type(out) is not exp.Alias or not (label := self.token(out.args["alias"]))
                    or type(out.this) is not exp.Column or out.this.db or out.this.catalog
                    or not self.token(out.this.this) or not self.token(out.this.args.get("table"))
                    or out.this.table.lower() != base_ref.alias_or_name.lower()
                    or transfer.get("kind") != "COLUMN_PASSTHROUGH"
                    or transfer["input"] != key("O",st,self.scope_ids[src],self.token(out.this.this))):
                continue
            terminal = record(transfer["input"], {})
            base = record(base_rel, {})
            if (terminal.get("kind") != "COLUMN_BINDING" or terminal["relation"] != base_rel
                    or terminal["qualifier"] != self.token(out.this.args["table"])
                    or terminal["endpoint"] != key("BASE",base_rel,terminal["column"])
                    or base.get("kind") != "ROW_INPUT" or record(local_rel, {}).get("kind") != "ROW_INPUT"
                    or (base["source"],terminal["column"]) != (u["source"],u["column"])):
                continue
            result.append(dict(use_index=i, call_span=read["anchor"], literal_span=read["literal"],
                path_tokens=u["path_tokens"], consumer=dict(statement=st,scope=sc,slot=slot), anchor=anchor,
                relation=dict(scope=sc,declaration_span=local_rel[-1],reference_name_span=self.token(local_ref.this)),
                producer=dict(statement=st,scope=port[-2],slot=port[-1],output_name_span=label,cte_name_span=cte_name),
                terminal=dict(kind="SQL_QUALIFIED_BASE_REFERENCE",source=base["source"],column=terminal["column"],
                              scope=base_rel[-2],declaration_span=base["anchor"],table_part_spans=base["parts"],
                              qualifier_span=terminal["qualifier"],column_span=terminal["anchor"])))
        return result


def observe(sql, *, source_schemas=None):
    """Return (ordinary facts, detached private evidence). No SQL rewrite, lookup, cache or route."""
    side = dict(version=VERSION,basis="SAME_RUN_SINGLE_INPUT_CTE_SLOT",catalog_verified=False,witnesses=[])
    if len(sql) > 32_768:
        return analyze_subfields(sql,"spark",source_schemas), side
    a = Capture(sql,"spark",source_schemas,Limits(edges=512, memo_bytes=128*1024))
    public = a.run()
    side["snapshot"] = a.shadow.snapshot
    try:
        side["witnesses"] = deepcopy(a.witnesses(public))
    except Exception:
        # An unsupported or interrupted shadow is never evidence. Preserve the
        # already completed ordinary result; do not start a fallback parse.
        side["reason"] = "SHADOW_UNAVAILABLE"
    return public, side
